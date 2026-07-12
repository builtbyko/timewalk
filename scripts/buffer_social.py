#!/usr/bin/env python3
"""Validate and queue TimeWalk social posts through Buffer's GraphQL API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

API_URL = "https://api.buffer.com"
DEFAULT_POSTS_FILE = Path("social/posts.json")
VALID_STATUSES = {"draft", "ready", "queued", "cancelled"}


class SocialPostError(RuntimeError):
    """Raised when post data or Buffer API responses are invalid."""


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects so the Buffer bearer token never reaches another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise SocialPostError(
            f"Buffer API unexpectedly redirected the request (HTTP {code})."
        )


def parse_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SocialPostError(f"Invalid ISO 8601 datetime: {value}") from exc
    if parsed.tzinfo is None:
        raise SocialPostError(f"Datetime must include a timezone offset: {value}")
    return parsed.astimezone(timezone.utc)


def load_document(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SocialPostError(f"Posts file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SocialPostError(
            f"Invalid JSON in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(data, dict):
        raise SocialPostError("The posts file must contain a JSON object.")
    return data


def save_document(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(serialized)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def validate_document(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("version") != 1:
        errors.append("Top-level 'version' must be 1.")

    posts = data.get("posts")
    if not isinstance(posts, list):
        return errors + ["Top-level 'posts' must be a list."]

    seen_ids: set[str] = set()
    for index, post in enumerate(posts):
        prefix = f"posts[{index}]"
        if not isinstance(post, dict):
            errors.append(f"{prefix} must be an object.")
            continue

        post_id = post.get("id")
        if not isinstance(post_id, str) or not post_id.strip():
            errors.append(f"{prefix}.id must be a non-empty string.")
        elif post_id in seen_ids:
            errors.append(f"Duplicate post id: {post_id}")
        else:
            seen_ids.add(post_id)

        text = post.get("text")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{prefix}.text must be a non-empty string.")
        elif len(text) > 280:
            errors.append(
                f"{prefix}.text is {len(text)} characters; keep it at 280 or fewer."
            )

        publish_at = post.get("publish_at")
        if not isinstance(publish_at, str):
            errors.append(f"{prefix}.publish_at must be an ISO 8601 string.")
        else:
            try:
                parse_datetime(publish_at)
            except SocialPostError as exc:
                errors.append(f"{prefix}.publish_at: {exc}")

        approved = post.get("approved")
        if not isinstance(approved, bool):
            errors.append(f"{prefix}.approved must be true or false.")

        status = post.get("status")
        if status not in VALID_STATUSES:
            errors.append(
                f"{prefix}.status must be one of: {', '.join(sorted(VALID_STATUSES))}."
            )

        if status == "ready" and approved is not True:
            errors.append(f"{prefix} is ready but not approved.")
        if approved is True and status == "draft":
            errors.append(f"{prefix} is approved but still marked as draft.")

        source_url = post.get("source_url")
        if status == "ready":
            if not isinstance(source_url, str) or not source_url.startswith("https://"):
                errors.append(
                    f"{prefix}.source_url must be an https URL before a post is ready."
                )

        image = post.get("image")
        if image is not None:
            if not isinstance(image, dict):
                errors.append(f"{prefix}.image must be an object or null.")
            else:
                url = image.get("url")
                if not isinstance(url, str) or not url.startswith("https://"):
                    errors.append(f"{prefix}.image.url must be a public https URL.")
                if status == "ready" and image.get("rights_confirmed") is not True:
                    errors.append(
                        f"{prefix}.image.rights_confirmed must be true before queuing."
                    )
                if status == "ready":
                    license_text = image.get("license")
                    source = image.get("source")
                    if not isinstance(license_text, str) or not license_text.strip():
                        errors.append(
                            f"{prefix}.image.license is required before queuing."
                        )
                    if not isinstance(source, str) or not source.strip():
                        errors.append(
                            f"{prefix}.image.source is required before queuing."
                        )

        if status == "queued":
            if not post.get("buffer_post_id") or not post.get("queued_at"):
                errors.append(
                    f"{prefix} is queued but buffer_post_id or queued_at is missing."
                )

    return errors


def graphql_request(api_key: str, query: str) -> dict[str, Any]:
    request = urllib.request.Request(
        API_URL,
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "TimeWalk-Social-Publisher/1.0",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(NoRedirectHandler())
    try:
        with opener.open(request, timeout=30) as response:
            actual_url = urllib.parse.urlparse(response.geturl())
            expected_url = urllib.parse.urlparse(API_URL)
            if (actual_url.scheme, actual_url.netloc) != (
                expected_url.scheme,
                expected_url.netloc,
            ):
                raise SocialPostError("Buffer API response came from an unexpected host.")
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SocialPostError(f"Buffer API HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SocialPostError(f"Could not reach Buffer API: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise SocialPostError("Buffer API returned invalid JSON.") from exc

    if payload.get("errors"):
        messages = "; ".join(
            str(error.get("message", error)) for error in payload["errors"]
        )
        raise SocialPostError(f"Buffer GraphQL error: {messages}")
    return payload


def gql_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def create_buffer_post(
    *,
    api_key: str,
    channel_id: str,
    text: str,
    due_at: datetime,
    image_url: str | None,
) -> str:
    asset_block = ""
    if image_url:
        asset_block = (
            "\n          assets: [{ image: { url: "
            + gql_string(image_url)
            + " } }]"
        )

    query = f"""
mutation CreatePost {{
  createPost(
    input: {{
      text: {gql_string(text)}
      channelId: {gql_string(channel_id)}
      schedulingType: automatic
      mode: customScheduled
      dueAt: {gql_string(due_at.isoformat().replace("+00:00", "Z"))}{asset_block}
    }}
  ) {{
    __typename
    ... on PostActionSuccess {{
      post {{
        id
        text
      }}
    }}
    ... on MutationError {{
      message
    }}
  }}
}}
"""
    payload = graphql_request(api_key, query)
    result = payload.get("data", {}).get("createPost")
    if not isinstance(result, dict):
        raise SocialPostError("Buffer API response did not include createPost data.")
    if result.get("message"):
        raise SocialPostError(f"Buffer rejected the post: {result['message']}")
    post = result.get("post")
    if not isinstance(post, dict) or not post.get("id"):
        raise SocialPostError("Buffer API response did not include a post id.")
    return str(post["id"])


def list_channels(api_key: str) -> None:
    organization_query = """
query GetOrganizations {
  account {
    organizations {
      id
    }
  }
}
"""
    payload = graphql_request(api_key, organization_query)
    organizations = payload.get("data", {}).get("account", {}).get("organizations", [])
    if not organizations:
        raise SocialPostError("No Buffer organizations were found for this API key.")

    rows: list[dict[str, str]] = []
    for organization in organizations:
        organization_id = organization.get("id")
        if not organization_id:
            continue
        channel_query = f"""
query GetChannels {{
  channels(input: {{ organizationId: {gql_string(str(organization_id))} }}) {{
    id
    name
    displayName
    service
    isQueuePaused
  }}
}}
"""
        channel_payload = graphql_request(api_key, channel_query)
        channels = channel_payload.get("data", {}).get("channels", [])
        for channel in channels or []:
            rows.append(
                {
                    "organization_id": str(organization_id),
                    "channel_id": str(channel.get("id", "")),
                    "service": str(channel.get("service", "")),
                    "name": str(
                        channel.get("displayName") or channel.get("name") or ""
                    ),
                    "queue_paused": str(channel.get("isQueuePaused", False)),
                }
            )

    if not rows:
        raise SocialPostError("No channels were found. Connect X to Buffer first.")

    print(json.dumps(rows, ensure_ascii=False, indent=2))


def queue_posts(
    *,
    path: Path,
    lookahead_hours: float,
    max_posts: int,
    dry_run: bool,
) -> int:
    data = load_document(path)
    errors = validate_document(data)
    if errors:
        raise SocialPostError("\n".join(f"- {error}" for error in errors))

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=lookahead_hours)
    late_grace = now - timedelta(minutes=15)

    candidates: list[tuple[datetime, dict[str, Any]]] = []
    for post in data["posts"]:
        if post.get("approved") is not True or post.get("status") != "ready":
            continue
        publish_at = parse_datetime(post["publish_at"])
        if publish_at < late_grace:
            print(
                f"SKIP {post['id']}: publish_at is more than 15 minutes in the past.",
                file=sys.stderr,
            )
            continue
        if publish_at <= cutoff:
            candidates.append((publish_at, post))

    candidates.sort(key=lambda item: item[0])
    candidates = candidates[:max_posts]

    if not candidates:
        print("No approved posts are due within the lookahead window.")
        return 0

    if dry_run:
        for publish_at, post in candidates:
            image_note = " with image" if post.get("image") else ""
            print(
                f"DRY RUN: would queue {post['id']} for "
                f"{publish_at.isoformat()}{image_note}"
            )
        return 0

    api_key = os.environ.get("BUFFER_API_KEY", "").strip()
    channel_id = os.environ.get("BUFFER_CHANNEL_ID", "").strip()
    if not api_key:
        raise SocialPostError("BUFFER_API_KEY is not set.")
    if not channel_id:
        raise SocialPostError("BUFFER_CHANNEL_ID is not set.")

    queued_count = 0
    for publish_at, post in candidates:
        image = post.get("image")
        image_url = image.get("url") if isinstance(image, dict) else None
        buffer_post_id = create_buffer_post(
            api_key=api_key,
            channel_id=channel_id,
            text=post["text"],
            due_at=publish_at,
            image_url=image_url,
        )
        post["status"] = "queued"
        post["buffer_post_id"] = buffer_post_id
        post["queued_at"] = now.isoformat().replace("+00:00", "Z")
        queued_count += 1
        print(f"QUEUED {post['id']} as Buffer post {buffer_post_id}")

    save_document(path, data)
    return queued_count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--posts-file",
        type=Path,
        default=DEFAULT_POSTS_FILE,
        help=f"Path to posts JSON (default: {DEFAULT_POSTS_FILE})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate", help="Validate the posts file.")

    subparsers.add_parser(
        "channels", help="List Buffer organizations and channels."
    )

    queue_parser = subparsers.add_parser(
        "queue", help="Queue approved posts that are due soon."
    )
    queue_parser.add_argument("--lookahead-hours", type=float, default=36)
    queue_parser.add_argument("--max-posts", type=int, default=2)
    queue_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.environ.get("DRY_RUN", "").lower() == "true",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "validate":
            data = load_document(args.posts_file)
            errors = validate_document(data)
            if errors:
                raise SocialPostError("\n".join(f"- {error}" for error in errors))
            print(f"Validated {len(data['posts'])} post(s) in {args.posts_file}.")
            return 0

        if args.command == "channels":
            api_key = os.environ.get("BUFFER_API_KEY", "").strip()
            if not api_key:
                raise SocialPostError("Set BUFFER_API_KEY to list channels.")
            list_channels(api_key)
            return 0

        if args.command == "queue":
            if args.lookahead_hours <= 0:
                raise SocialPostError("--lookahead-hours must be greater than zero.")
            if args.max_posts <= 0 or args.max_posts > 10:
                raise SocialPostError("--max-posts must be between 1 and 10.")
            queue_posts(
                path=args.posts_file,
                lookahead_hours=args.lookahead_hours,
                max_posts=args.max_posts,
                dry_run=args.dry_run,
            )
            return 0

        parser.error("Unknown command")
        return 2
    except SocialPostError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
