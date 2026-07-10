# -*- coding: utf-8 -*-
"""
ginza_build.py — TimeWalk 銀座ページのビルド
実行: python ginza_build.py  (scripts/ フォルダから)
出力: ../ginza/index.html (マップ + 解説統合の1ページ)

v3(2026-07-07): アーキテクチャをfolium直接描画からGeoJSON生成+
scripts/ginza_template.html への注入方式に移行。タイムスライダー、
視点場・時のアンカー・いまも食える歴史レイヤを追加。

レイヤ構成(ストーリー: §notes/ginza.md 参照):
  1. 夜の銀座(推定エリア)           … 集積③: 並木通り周辺のクラブ・バー集積
  2. 鉄道・駅(OSM現況)             … 現在地の手がかり
  3. 消えた川と堀(推定線・破線)    … 痕跡①: 銀座は水に囲まれた島だった
  4. 歩く空間の網(OSM現況)         … 骨格②の裏側: グリッドの裏に残る路地
  5. 視点場(手動データ)           … 視点場⑧: 「ここに立って、これを見る」
  6. 時のアンカー(OSM稲荷+手動建築) … 定点⑦: 稲荷・戦前建築
  7. いまも食える歴史(手動データ)   … 集積③: 現役の老舗飲食店
  8. ギャラリー・アート(OSM+手動)   … 集積③: いまの銀座の顔
ベースマップ: ダーク(標準)/淡色の2択 + タイムスライダーで航空写真4時代を連続補間
"""

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import map_toolkit as tk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "..", "ginza")
OUT_HTML = os.path.join(OUT_DIR, "index.html")
CACHE_DIR = os.path.join(BASE_DIR, "..", "data")
TEMPLATE_PATH = os.path.join(BASE_DIR, "ginza_template.html")

USE_CACHE = True

# 銀座 約1km四方
BBOX = (35.6645, 139.7590, 35.6755, 139.7720)
CENTER = ((BBOX[0] + BBOX[2]) / 2, (BBOX[1] + BBOX[3]) / 2)

# ---------------------------------------------------------------
# 消えた川と堀(推定線)。外堀・汐留川・京橋川はKK線現況線形の代理トレース、
# 三十間堀川は1945-50空中写真照合済み。4本は合流点で頂点共有(「島」が閉じる)。
# ---------------------------------------------------------------
LOST_WATERWAYS = [
    ("三十間堀川(1948-49年 戦災瓦礫で埋立)", [
        (35.674227, 139.771503), (35.6735, 139.7705),
        (35.6710, 139.7684), (35.6685, 139.7663), (35.6662, 139.7645),
    ]),
    ("汐留川(埋立→上に東京高速道路)", [
        (35.6693, 139.7573), (35.668124, 139.759030),
        (35.667144, 139.762024), (35.666073, 139.762910), (35.6662, 139.7645),
    ]),
    ("京橋川(埋立→上に東京高速道路)", [
        (35.675773, 139.766432), (35.675004, 139.769401), (35.674227, 139.771503),
    ]),
    ("外堀(埋立→外堀通り・高速)", [
        (35.668124, 139.759030), (35.672145, 139.760612),
        (35.672499, 139.761126), (35.673305, 139.764029),
        (35.675699, 139.765588), (35.675773, 139.766432),
    ]),
]

# ---------------------------------------------------------------
# ギャラリー手動プロット。OSM収録39件が閾値50件未満のため未収録5件を追加。
# ---------------------------------------------------------------
MANUAL_GALLERIES = [
    ("資生堂ギャラリー", 35.66858, 139.76190),
    ("ギンザ・グラフィック・ギャラリー(ggg)", 35.66975, 139.76254),
    ("シャネル・ネクサス・ホール", 35.67294, 139.76663),
    ("ポーラ ミュージアム アネックス", 35.67425, 139.76799),
    ("ギャラリー小柳", 35.67465, 139.76817),
]

# ---------------------------------------------------------------
# 夜の銀座(推定エリア)。並木通り軸・6〜8丁目西側を街区方位に合わせた概略。
# ---------------------------------------------------------------
NIGHT_GINZA = [
    (35.6700, 139.7598), (35.6700, 139.7622),
    (35.6660, 139.7604), (35.6660, 139.7581),
]

# ---------------------------------------------------------------
# 視点場(v3新規、初期表示ON)。「ここに立って、これを見る」7点。
# 座標は住所の無い体感ポイントのため目算の推定(§1-5相当)。
# ---------------------------------------------------------------
VIEWPOINTS = [
    ("晴海通り、4丁目交差点そば(築地方向を望む)", 35.6716, 139.7648,
     "銀座が乗るのは、かつて日比谷入江と隅田川河口に挟まれた砂州「江戸前島」の上。"
     "中央通りはその尾根筋にあたり、徳川家康の都市計画では排水の利便からこの微高地に"
     "沿って主軸道路(現・中央通り)が通された。晴海通りを東(築地方向)へ向かうと感じる"
     "わずかな下り勾配は、岬の先端へ降りていく地形の記憶そのものだ。"
     "1604年にはこの尾根筋を通って東海道が延伸されている。"),
    ("中央通りの街区(間口の細かさを見る)", 35.6706, 139.7638,
     "江戸の町人地は「京間60間四方」の正方形街区が基本単位で、中央に会所地(空き地)を"
     "置き、通り沿いに奥行20間の町屋敷を並べた。店の奥、会所地へ入る通路が路地の起源。"
     "明治の銀座煉瓦街もこの江戸の地割をほぼ踏襲し、通りと平行なI字型の路地を新たに"
     "加えた。ビルの間口の細かさを目で追うと、江戸の敷地割りが今も生きているのがわかる。"),
    ("金春通り(金春湯・通り名プレート)", 35.66829, 139.76118,
     "この通りの名は、江戸時代に能楽金春流の屋敷がここにあったことに由来する。"
     "金春家は寛永4年(1627)に屋敷を拝領し、幕末に麹町へ移転した後、「金春芸者」の名で"
     "知られる花街となった。現存する金春湯は文久3年(1863)創業。"
     "金春屋敷→金春芸者→新橋花街→戦後の高級クラブ街という、銀座の「夜」の"
     "400年近い系譜がこの130mの通りに凝縮されている。"),
    ("4丁目交差点(スカイラインを見上げる)", 35.6716, 139.7648,
     "ぐるりと見渡すと、周囲のビルの高さがおおむね揃っていることに気づく。"
     "1998年、銀座通連合会と中央区が地区計画「銀座ルール」を定め、幹線道路沿いの"
     "建物高さを最高56mに制限。2006年には銀座デザイン協議会との協議も義務化された。"
     "日本一の地価を持つ街が、自ら容積・高さ・意匠を抑制している——放任ではなく、"
     "ルールと運営で作られ続けているまちの実例がここにある。"),
    ("昭和通りを東へ(歌舞伎座方向、旧木挽町境界)", 35.6695, 139.7668,
     "この通りの下には、かつて銀座と隣町「木挽町」を隔てていた三十間堀川が流れていた。"
     "木挽町は江戸城修築の木挽職人に由来する芝居町で、歌舞伎座があるのはその名残。"
     "1952年、埋め立てで銀座と地続きになった木挽町は町名ごと消え、銀座1〜8丁目に"
     "編入された。渡った先の空気の変わり方に、消えた川がいまも境界として"
     "働いているのを感じられる。"),
    ("コリドー街高架下(旧KK線)", 35.6663, 139.7598,
     "頭上の構造物は、外堀・汐留川・京橋川を埋め立てて1951年に建設された"
     "東京高速道路(KK線)。「川→高速道路→2025年廃止→歩行者空間」という三段階の"
     "変化が、ここでは頭上の構造物としてそのまま重なって見える。KK線は2025年4月5日に"
     "道路として廃止され、Tokyo Sky Corridorへの転換が始まった。"),
    ("日曜の4丁目交差点(歩行者天国)", 35.6716, 139.7648,
     "1970年8月2日、銀座・新宿・池袋・浅草の4地区で日本初の歩行者天国が始まった。"
     "半世紀を超えて続く、日本のホコ天の元祖級。日曜(祝日を含む)の実施時間帯だけ、"
     "ふだん車が行き交う交差点の真ん中に立って和光を見上げることができる——"
     "道路が広場に変わる、時間限定の視点場だ。"),
]

# ---------------------------------------------------------------
# 時のアンカー: 建築5件(v3新規)。既存のOSM稲荷データと同一レイヤに合流する。
# 座標は地理院住所検索APIで取得済み。
# ---------------------------------------------------------------
ANCHOR_BUILDINGS = [
    ("和光(時計塔)", 35.67160, 139.76483,
     "1932年(昭和7)竣工、設計は渡辺仁。旧服部時計店本社ビルで、四方の文字盤が"
     "ほぼ正確に東西南北を向く。関東大震災後の輝きを取り戻すために建てられ、"
     "銀座4丁目交差点のランドマークとして今も時を刻み続けている。"),
    ("奥野ビル", 35.67374, 139.76880,
     "1932年築の本館・1934年築の新館からなる、旧「銀座アパートメント」。"
     "民間住居では日本初とされるエレベーターは二重扉の手動式で、階数表示は"
     "今も針指し式のまま現役。かつての高級アパートは、いまギャラリーやショップが"
     "数十軒入る名物ビルになっている。"),
    ("教文館ビル", 35.67224, 139.76552,
     "設計はアントニン・レーモンド、1933年(昭和8)竣工のアール・デコ建築。"
     "1885年創業のキリスト教書籍・洋書の老舗書店が、いまも銀座で唯一の"
     "路面書店として営業を続ける。"),
    ("ビヤホールライオン銀座七丁目店", 35.66926, 139.76315,
     "1934年創建、現存する日本最古のビヤホール。設計は新橋演舞場も手がけた"
     "菅原栄蔵。縦2.75m×横5.75m、約250色のガラスモザイク壁画は日本初。"
     "2022年、建物(銀座ライオンビル)は国の登録有形文化財に指定された。"
     "いまも現役の飲食店として営業中。"),
    ("泰明小学校", 35.67206, 139.76112,
     "関東大震災で校舎を失い、1929年(昭和4)に再建された復興小学校。"
     "曲面壁とアーチ窓を持つモダニズム建築で、東京都選定歴史的建造物にも"
     "選ばれている。140年以上の歴史を持ちながら、いまも現役の公立小学校として"
     "子どもたちが通っている。"),
]

# 既存OSM稲荷の一部に個別の解説文を当てる(該当なしは既定文)
SHRINE_NOTES = {
    "豊岩稲荷神社": "江戸初期からこの地にあり、火防・縁結びの神として"
                    "路地の中で商売の街を見守ってきた。",
    "朝日稲荷神社": "関東大震災後、御神体が三十間堀川の川底から現れたと伝わる。",
    "あづま稲荷大明神": "三原小路の奥にひっそりと祀られる。",
}
DEFAULT_SHRINE_NOTE = ("ビルの谷間や屋上に残る小さな稲荷・神社。秋の"
                       "「銀座八丁神社めぐり」で巡られる社の一つ。")

# ---------------------------------------------------------------
# いまも食える歴史(v3新規、初期表示OFF)。ビヤホールライオンは時のアンカーに
# 既に含まれるため重複させない(アンカー側のdescに現役飲食店の旨を明記済み)。
# ---------------------------------------------------------------
FOOD_HISTORY = [
    ("煉瓦亭", 35.67273, 139.76593,
     "1895年(明治28)創業の洋食店。オムライスやポークカツレツは、この店を起点に"
     "広まったとされる(発祥を巡っては異論もある)。まかない料理から生まれた"
     "オムライスの逸話は、いまも語り継がれている。"),
    ("資生堂パーラー 銀座本店", 35.66851, 139.76198,
     "1902年(明治35)、ソーダ水とアイスクリームを出す日本初の「ソーダファウンテン」"
     "として誕生。1928年に洋食レストランへ発展した。資生堂創業の地・銀座で"
     "120年以上、変わらぬ味を守り続けている。"),
    ("木村屋總本店 銀座本店", 35.67162, 139.76524,
     "1869年(明治2)創業。あんぱんの元祖として知られ、いまも大通りに店を構える"
     "明治創業の老舗の一つ。"),
    ("銀座ウエスト 本店", 35.67036, 139.76077,
     "1947年(昭和22)創業。戦後の物価統制でレストランから洋菓子・喫茶に転じ、"
     "看板商品のリーフパイやドライケーキで親しまれる。名曲を解説付きで流す"
     "「名曲の夕べ」など、文化人が集う店としても知られてきた。"),
    ("トリコロール本店", 35.67033, 139.76506,
     "1936年(昭和11)創業、90年近い歴史を持つ喫茶店。木村コーヒー店"
     "(現キーコーヒー)店主がコーヒー普及のために開いた店で、洋行帰りの"
     "芸術家や学生たちが集った。赤レンガの外観と木製回転扉、シャンデリアが"
     "昭和初期のカフェ文化を今に伝える。"),
    ("竹葉亭 銀座店", 35.67084, 139.76527,
     "嘉永年間、剣術道場の茶屋として創業。慶応2年(1866)に「竹葉亭」を名乗り、"
     "明治には歌舞伎座などへ弁当を納める鰻の名店に。関東大震災で被災後、"
     "1924年に木挽町(現・銀座)へ移転した。いまも鰻を食べられる。"),
    ("空也", 35.67090, 139.76280,
     "明治17年(1884)、上野池之端で創業。戦災を経て昭和24年(1949)、銀座6丁目・"
     "並木通りへ移転した。名物「空也もなか」は予約必須の人気で、夏目漱石"
     "『吾輩は猫である』をはじめ文学作品にもたびたび登場してきた。"),
]

# ---------------------------------------------------------------
# レイヤ表示の初期状態(実際のON/OFFは ginza_template.html の地図初期化コードで
# 反映済み。この辞書はビルドレポートでの確認用)
# ---------------------------------------------------------------
DEFAULT_SHOW = {
    "歩く空間の網": True,
    "消えた川と堀": True,
    "視点場": True,
    "鉄道・駅": True,
    "ギャラリー・アート": False,
    "時のアンカー": False,
    "いまも食える歴史": False,
    "夜の銀座": False,
}

# ---------------------------------------------------------------
# 解説カード(テンプレートの @@NARRATIVE_HTML@@ に注入する内容)
# ---------------------------------------------------------------
NARRATIVE_HTML = """<div class="tw-wrap" id="tw-notes">
<h1>銀座 — 消えた川の上を、歩く</h1>
<p class="catch">TimeWalk #01 | 過去から今への「まちの流れ」を読み、歩くマップ</p>

<section class="tw-card tw-fade">
<h2>このまちの特色</h2>
<p>銀座の名は、江戸初期にここへ置かれた銀貨鋳造所「銀座役所」に由来する。以来ここは
一貫して<b>商人の街</b>だ。あんぱんを生んだ木村屋(1869)、京都から来た香と書画の
鳩居堂(1880)、文具の伊東屋(1904)——明治に創業した老舗がいまも大通りに並び、
「鳩居堂前」の路線価は38年連続で日本一であり続けている。</p>
<p>いまの骨格を作ったのは明治の大火だ。1872(明治5)年の大火のあと政府は西洋式の
煉瓦街をここに建設し、広い直線街路のグリッドが引かれた。煉瓦の建物は関東大震災(1923)で
ほぼ失われたが、<b>グリッドだけが生き残り</b>、その大街区の裏に三原小路のような
細い路地が張り付いた——マップの琥珀色の網は、その現在の姿だ。</p>
<p>そしてもうひとつ。銀座はかつて<b>四方を川と堀に囲まれた「島」だった</b>。
京橋川・三十間堀川・汐留川・外堀。戦後、三十間堀川は戦災の瓦礫で埋め立てられ(1948-49)、
残る水辺の上には高速道路(KK線)が架かった。マップのシアンの破線は、その消えた水の
記憶のおよその位置だ。タイムスライダーを「1945-50」に動かすと、埋立前の川が
実際に写っているのが見える。</p>
<p>路地の奥にはもうひとつの銀座がいる。ビルの谷間や屋上に残る<b>小さな稲荷たち</b>
(朱色の点、鳥居の色)。豊岩稲荷は江戸初期からこの地にあり、火防・縁結びの神として
路地の中で商売の街を見守ってきた。秋には9社を巡る「銀座八丁神社めぐり」も行われる。</p>
<p class="legend">凡例:
<span style="color:#e8b84b">■ 歩く空間の網</span>
<span style="color:#3ec6f2">■ 消えた川と堀(推定)</span>
<span style="color:#3ec6f2">👁 視点場</span>
<span style="color:#ff5a3c">⛩ 時のアンカー(稲荷・戦前建築)</span>
<span style="color:#ff4fa3">🎨 ギャラリー・アート</span>
<span style="color:#e8b84b">🍴 いまも食える歴史</span>
<span style="color:#a78bff">▨ 夜の銀座(推定エリア)</span></p>
</section>

<section class="tw-card tw-fade">
<h2>まちの流れ(成り立ち → 現在)</h2>
<p><b>岬(地形):</b> 銀座が乗るのは、日比谷入江と隅田川河口に挟まれた砂州「江戸前島」。
中央通りはその尾根筋にあたり、徳川家康の都市計画はこの微高地に沿って主軸道路を
通すところから始まった——銀座は「島」である前に、まず「岬」だった。街のシンボルである
柳も、この土地の証言者だ。明治7年(1874)に日本初の街路樹として桜・松・楓を植えたが、
埋立地の湿った地盤ではうまく育たず、水に強い柳に植え替えられた。</p>
<p><b>江戸(1612〜):</b> 銀座役所が置かれ、地名が生まれる。町人地は京間60間四方の
正方形街区が基本単位で、中央の会所地(空き地)へ入る通路が、いまに残る路地の起源に
なった。</p>
<p><b>明治(1872〜):</b> 銀座大火 → 煉瓦街建設。江戸の地割りはほぼそのまま踏襲され、
そこに通りと平行なI字型の新しい路地が加わった。いま歩いている直線街路のグリッドは
このとき引かれた。木村屋・鳩居堂・伊東屋ら、いまも残る老舗が次々と店を構えた時代。
<i>→ ダーク地図で街路の直線性を確認</i></p>
<p><b>大正(1923):</b> 関東大震災で煉瓦街壊滅。骨格(街路)だけが残り、復興建築のまちへ。
朝日稲荷の御神体が三十間堀川の川底から現れたと伝わるのは、この震災の後のことだ。
泰明小学校や、木挽町から移った竹葉亭が現在地に落ち着いたのもこの震災後の時期にあたる。</p>
<p><b>昭和(1945〜):</b> 戦災、そして復興。三十間堀川が瓦礫で埋め立てられ(1948-49)、
木挽町は町名ごと銀座に編入されて消えた。外堀・汐留川・京橋川の上には東京高速道路
(KK線)が架かった。通行料を取らず、高架下の商業ビル(銀座ナイン・銀座コリドー街・
銀座ファイブなど)の賃料で運営される珍しい道路だ。川は消え、水辺は道路と商店街に
変わった。<i>→ タイムスライダーを 1945-50 → 1961-69 → 現在 と動かすと、川が消えていく
過程がそのまま見える</i></p>
<p><b>現在 → 未来:</b> 大街区の表は老舗と大型店、裏には路地と画廊と稲荷、7・8丁目には
金春芸者の系譜を引く夜の顔。この街は放任の結果ではなく、ルールと運営で作られ続けている
——1998年の地区計画「銀座ルール」は建物高さを56mに抑え、2006年設立の銀座デザイン
協議会が意匠まで協議する。1970年開始の歩行者天国は半世紀を超えて続き、地方自治体の
アンテナショップが銀座・有楽町に集まるのも、この街が保ち続ける求心力の現在形だ。
そしてKK線は<b>2025年4月5日に道路として廃止</b>され、歩行者空間「<b>Tokyo Sky
Corridor</b>」への転換が始まった(2030〜40年代に整備予定)。川だった場所が、道路を
経て、こんどは空中の遊歩道になる。</p>
</section>

<section class="tw-card tw-fade">
<h2>丁目の歩き方</h2>
<dl class="tw-choume">
<dt>1〜2丁目(京橋寄り)</dt>
<dd>画廊がもっとも濃いエリア。ギャラリー小柳、ポーラ ミュージアム アネックス、
約20軒の画廊が入る奥野ビル(1932年築の元高級アパート)が徒歩数分圏に固まる。
ピンクの点の集まり方で確かめてほしい。</dd>
<dt>3〜4丁目(中心)</dt>
<dd>松屋・三越と4丁目交差点。日本一の路線価「鳩居堂前」もここ。並木通りの東裏に
宝童稲荷、松屋通りに朝日稲荷——表通りの一本裏で朱色の点を探しながら歩くエリア。</dd>
<dt>5〜6丁目(大型商業)</dt>
<dd>GINZA SIXなど大型商業の並び。三原小路の奥にあづま稲荷。表の大街区と裏の路地の
コントラストがいちばん体感しやすい。</dd>
<dt>7〜8丁目(新橋寄り)</dt>
<dd>資生堂の足元、ggg(グラフィックデザインの専門ギャラリー)。すずらん通り裏の
路地に豊岩稲荷。金春通りには、江戸期に能楽金春流の屋敷があった名残が今も通り名に
残る——屋敷は幕末に麹町へ移り、跡地は「金春芸者」の花街になった。これが新橋花街を
経て、戦後の高級クラブ街へとつながる系譜だ。夜は並木通り周辺がクラブ・バーの
集まる「夜の銀座」の中心になる(紫のエリアはそのおよその範囲)。多くは会員制・
紹介制で一見の客を入れないが、政財界人や文人たちの社交場として機能してきた
歴史を持つ。高架下のコリドー街はKK線の記憶ごと飲める場所。</dd>
</dl>
</section>

<section class="tw-closing tw-fade">
<p class="tw-closing-lead">最後に、ひとつだけ</p>
<p>ここまで読んだあなたは、もう最初のあなたではない。</p>
<p>さっきまで、ただのビルの細い隙間だったものが、いまは江戸の地割の裂け目に
見える。ただの高速道路の高架が、川の亡骸に見える。</p>
<p>そこで、最後にひとつだけ試してほしい。</p>
<p>下のボタンを押すと、地図は1945年の銀座に戻る。一面の焼け跡だ。
グリッドだけが残り、三十間堀川にはまだ水がある。</p>
<p>そこから、ゆっくりスライダーを右へ。</p>
<p>川が埋まる。高速道路が架かる。ビルが建ち、入れ替わり、いまの銀座になる——
<span class="tw-closing-emphasis">80年が、あなたの親指の下で流れる。</span></p>
<button id="tw-closing-btn" class="tw-closing-btn" type="button">
<span class="tw-closing-logo">TIMEWALK</span>▶ 1945年の銀座から、もう一度</button>
</section>

<section class="tw-card tw-fade">
<h2>データと手法</h2>
<p class="src">
・歩く空間の網: © OpenStreetMap contributors(Overpass APIで取得。
footway / pedestrian / alley 等を「雰囲気優先」で広めに抽出)<br>
・ギャラリー: © OpenStreetMap contributors + 主要ギャラリー5件を手動追加
(位置はOSM収録の建物・施設および地理院の住所検索による)<br>
・時のアンカー: 稲荷・小社は© OpenStreetMap contributors(place_of_worship / shinto)。
戦前建築5件(和光・奥野ビル・教文館・ビヤホールライオン銀座七丁目店・泰明小学校)は
座標を地理院住所検索APIで取得し手動追加。出典は各公式サイト・Wikipedia等<br>
・視点場: 座標は住所のない体感ポイントのため目算の推定。出典は江戸前島Wikipedia、
銀座街づくり会議、金春通り会、Rules.jp、東銀座エリアマネジメント、JAFメイト等<br>
・いまも食える歴史: 座標は地理院住所検索APIによる。出典は各店舗公式サイト・Wikipedia等<br>
・夜の銀座エリア: 位置・範囲は<b>推定</b>(破線・半透明の面で表現)。個別店舗は示さない<br>
・ベースマップ: ダーク/淡色 = CARTO dark_all / light_all、空中写真 = 国土地理院
(地理院タイル: seamlessphoto / gazo1 / ort_old10 / ort_USA10。タイムスライダーで
opacityを連続補間)<br>
・消えた川と堀: 位置は<b>推定</b>(破線で表現)。外堀・汐留川・京橋川は、川を埋め立てて
建設された東京高速道路(KK線)の現況線形を川筋の代理とし、三十間堀川は1945-50年
空中写真との照合で調整した。正確な流路をトレースしたものではない<br>
・本文の歴史記述の主な出典:
<a href="https://www.chuo-kanko.or.jp/pages/other_details/birthplace-of-ginza">中央区観光協会「銀座発祥の地」</a>、
<a href="https://www.soumu.metro.tokyo.lg.jp/01soumu-archives/07edo_tokyo/0701syoko_kara02">東京都公文書館「銀座煉瓦街関係書類」</a>、
<a href="https://www.city.chuo.lg.jp/a0013/kusei/kousoukeikaku/heiwajigyou/heiwavm/r5kikaku.html">中央区「中央区の戦後復興」</a>(三十間堀川の埋立は1948年6月〜1949年7月)、
<a href="https://www.toshiseibi.metro.tokyo.lg.jp/machizukuri/machi_project/toshi_saisei/kk_arikata">東京都都市整備局「東京高速道路(KK線)の再生」</a>、
<a href="https://www.tokyo-kousoku.jp/project/">東京高速道路株式会社</a>、
<a href="https://www.ginza-machidukuri.jp/column/29/">銀座街づくり会議「家康がつくった町割」</a>、
<a href="https://www.ginza-machidukuri.jp/column/36/">銀座街づくり会議「銀座は埋め立て地？」</a>、
<a href="https://www.rules.jp/detail.php?id=2">Rules.jp「銀座ルール」</a>、
<a href="https://www.komparu-ginza.com/history">金春通り会「金春通りの歴史」</a>、
<a href="https://www.higashiginza-area.com/">東銀座エリアマネジメント「木挽町の歴史」</a>、
<a href="https://jafmate.jp/car/car_anniversary_20250610.html">JAFメイト「歩行者天国」</a>、
<a href="https://www.ginza-web.com/contents/shrine/">銀座なび「銀座の神社」</a>、
<a href="https://www.ginzakimuraya.jp/history/">銀座木村家</a>、
<a href="https://www.ito-ya.co.jp/story/history.html">伊東屋</a>、
<a href="https://www.nikkei.com/article/DGXMZO46789680R00C19A7CC0000/">日本経済新聞(鳩居堂前・路線価)</a>、
<a href="https://gallery.shiseido.com/jp/access/">SHISEIDO GALLERY</a>、
<a href="https://www.tokyoartbeat.com/articles/-/galleryguide_ginza_marunouchi">Tokyo Art Beat</a><br>
・コードと手法: <a href="https://github.com/builtbyko/timewalk">GitHub: builtbyko/timewalk</a>
</p>
</section>
</div>"""


def geojson_js(varname, fc):
    """GeoJSON FeatureCollectionをJS定数定義の文字列にする。
    </script>混入対策で "</" を "<\\/" にエスケープする。"""
    payload = json.dumps(fc, ensure_ascii=False).replace("</", "<\\/")
    return f"const {varname} = {payload};"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    # --- データ取得 ---
    walk_data = tk.overpass(
        tk.walk_net_query(BBOX),
        os.path.join(CACHE_DIR, "_overpass_ginza_walk_cache.json"), USE_CACHE)
    nodes = tk.node_index(walk_data)
    walk_ways = tk.simplify_ways(tk.extract_ways(walk_data, nodes))

    b = f"{BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]}"
    art_query = f"""[out:json][timeout:60];
(
  node["tourism"="gallery"]({b}); way["tourism"="gallery"]({b});
  node["shop"="art"]({b});        way["shop"="art"]({b});
  node["tourism"="artwork"]({b});
);
out body; >; out skel qt;"""
    art_data = tk.overpass(
        art_query,
        os.path.join(CACHE_DIR, "_overpass_ginza_art_cache.json"), USE_CACHE)
    art_pts = tk.extract_points(art_data, tk.node_index(art_data))

    rail_data = tk.overpass(
        tk.rail_query(BBOX),
        os.path.join(CACHE_DIR, "_overpass_ginza_rail_cache.json"), USE_CACHE)
    rail_ways, stations = tk.process_railways(rail_data)

    shrine_query = f"""[out:json][timeout:60];
(
  node["amenity"="place_of_worship"]["religion"="shinto"]({b});
  way["amenity"="place_of_worship"]["religion"="shinto"]({b});
);
out body; >; out skel qt;"""
    shrine_data = tk.overpass(
        shrine_query,
        os.path.join(CACHE_DIR, "_overpass_ginza_shrine_cache.json"), USE_CACHE)
    shrine_pts = tk.extract_points(shrine_data, tk.node_index(shrine_data))

    # --- 件数レポート ---
    print(f"[report] 歩く網: {len(walk_ways)} ways "
          f"({Counter(t.get('service', t.get('highway')) for t, _ in walk_ways).most_common(3)})")
    named_shrines = sum(1 for t, _, _ in shrine_pts if t.get("name"))
    print(f"[report] 時のアンカー: 稲荷{len(shrine_pts)}件(名前あり{named_shrines}) "
          f"+ 建築{len(ANCHOR_BUILDINGS)}件 = {len(shrine_pts) + len(ANCHOR_BUILDINGS)}件")
    art_total = len(art_pts) + len(MANUAL_GALLERIES)
    art_named = sum(1 for t, _, _ in art_pts if t.get("name")) + len(MANUAL_GALLERIES)
    print(f"[report] ギャラリー: {art_total} 地点(名前あり {art_named}、うち手動 {len(MANUAL_GALLERIES)})")
    print(f"[report] 視点場: {len(VIEWPOINTS)} 地点")
    print(f"[report] いまも食える歴史: {len(FOOD_HISTORY)} 地点")
    print(f"[report] 初期表示ON: {[k for k, v in DEFAULT_SHOW.items() if v]}")
    print(f"[report] 初期表示OFF: {[k for k, v in DEFAULT_SHOW.items() if not v]}")

    # --- GeoJSON変換 ---
    walknet_fc = tk.ways_to_geojson(walk_ways)
    rivers_fc = tk.lines_named_to_geojson(LOST_WATERWAYS)

    gallery_osm_fc = tk.points_to_geojson(art_pts)
    gallery_manual_fc = tk.points_to_geojson(
        [({"name": name}, lat, lon) for name, lat, lon in MANUAL_GALLERIES])
    gallery_fc = tk.merge_feature_collections(gallery_osm_fc, gallery_manual_fc)

    shrine_items = []
    for tags, lat, lon in shrine_pts:
        name = tags.get("name", tags.get("name:en", ""))
        desc = SHRINE_NOTES.get(name, DEFAULT_SHRINE_NOTE)
        shrine_items.append((name, lat, lon, desc))
    shrine_fc = tk.manual_points_to_geojson(shrine_items, kind="shrine")
    building_fc = tk.manual_points_to_geojson(ANCHOR_BUILDINGS, kind="building")
    anchors_fc = tk.merge_feature_collections(shrine_fc, building_fc)

    viewpoints_fc = tk.manual_points_to_geojson(VIEWPOINTS)
    food_fc = tk.manual_points_to_geojson(FOOD_HISTORY)
    night_fc = tk.polygon_to_geojson(NIGHT_GINZA, "夜の銀座(クラブ・バー集積)")

    rail_lines_fc = tk.ways_to_geojson(rail_ways, keep=("name", "railway", "tunnel"))
    rail_stations_fc = tk.points_to_geojson(stations)

    data_js = "\n".join([
        geojson_js("DATA_WALKNET", walknet_fc),
        geojson_js("DATA_RIVERS", rivers_fc),
        geojson_js("DATA_GALLERY", gallery_fc),
        geojson_js("DATA_ANCHORS", anchors_fc),
        geojson_js("DATA_VIEWPOINTS", viewpoints_fc),
        geojson_js("DATA_FOOD", food_fc),
        geojson_js("DATA_NIGHT", night_fc),
        geojson_js("DATA_RAIL_LINES", rail_lines_fc),
        geojson_js("DATA_RAIL_STATIONS", rail_stations_fc),
    ])

    # --- テンプレートへ注入 ---
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    html = (html
            .replace("@@TITLE@@", "銀座 — 消えた川の上を、歩く | TimeWalk")
            .replace("@@CENTER_LAT@@", str(CENTER[0]))
            .replace("@@CENTER_LON@@", str(CENTER[1]))
            .replace("@@HERO_KANJI@@", "銀座")
            .replace("@@HERO_EYEBROW@@", "TIMEWALK #01")
            .replace("@@HERO_LATIN_HTML@@", 'G<span class="hero-flicker">I</span>NZA')
            .replace("@@HERO_META@@", "消えた川の上を、歩く　35.6700N 139.7655E")
            .replace("@@NARRATIVE_HTML@@", NARRATIVE_HTML)
            .replace("@@DATA_JS@@", data_js))

    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    kb = os.path.getsize(OUT_HTML) / 1024
    print(f"[map] {os.path.basename(OUT_HTML)} ({kb:,.0f} KB)"
          + ("  → 2MB超・要軽量化" if kb > 2048 else "  → OK" if kb <= 1024 else "  → 1MB超・注意"))
    print(f"[done] {os.path.abspath(OUT_HTML)}")


if __name__ == "__main__":
    main()
