/* =====================================================================
 * CCNA Quest - 恋活モード (マッチングアプリ風 恋愛シミュレーション)
 *   「NetMatch」= Pairs/タップル風のマッチングアプリ。
 *   ヒロインは各CCNA分野のネットワークエンジニア。
 *   スワイプでいいね → マッチ → チャット(CCNAトークで好感度UP) →
 *   デートに誘う、というギャルゲー風の進行。
 *
 * 好感度(aff)は正解や良い返答で上昇。しきい値(gate)を超えると
 * デートに進める。最後は告白でエンディング。
 * ===================================================================== */

/* ヒロイン定義 (face は faces.js の style) */
const HEROINES = [
  {
    id: "akari", name: "あかり", age: 25, domain: "connectivity",
    job: "ネットワークエンジニア", tagline: "最適なルート、一緒に見つけよ？",
    bio: "ルーティングが得意。OSPFの美しさに惚れてます。休日はカフェで資格の勉強。理屈っぽいってよく言われる😌",
    face: { skin: "#ffe0d0", hair: "#3a3f5c", hair2: "#2a2e44", eyes: "#4a6fa5", hairstyle: "long", accessory: null, outfit: "#5b6ee0" },
    theme: "#5b6ee0",
    route: [
      { her: "マッチありがとう！あかりです😊 プロフィール見たけど、CCNA勉強してるんだ？", m: "happy" },
      { choice: [
        { t: "うん、実は君と同じで勉強中なんだ", aff: 6, reply: "ほんと!? 仲間だ〜！嬉しい🎉", m: "happy" },
        { t: "ネットワークの仕事に憧れてて", aff: 5, reply: "いいね、その気持ち大事にして！応援する✨", m: "happy" },
        { t: "正直プロフィールの写真で選んだ", aff: 1, reply: "ふふ、正直だね…ま、いっか😳", m: "shy" },
      ] },
      { her: "じゃあ早速だけど…ちょっとした確認クイズ、いい？私こういうの好きなの笑", m: "normal" },
      { q: { q: "同じ宛先をスタティック(AD1)・OSPF(AD110)・EIGRP(AD90)で学習したら、ルーティングテーブルに載るのは？", choices: ["OSPF", "EIGRP", "スタティック", "全部"], answer: 2, exp: "プレフィックス長が同じならAD最小が優先。スタティック(AD1)ね。" }, aff: 12 },
      { her: "正解率高いね！話してて楽しい〜。ねえ、休日ってなにしてるの？", m: "happy" },
      { choice: [
        { t: "だいたい家でラボ組んでるかな", aff: 7, reply: "え、最高じゃん!! 私も自宅にルータ3台あるよ🤭", m: "love" },
        { t: "普通に映画とか", aff: 4, reply: "いいね〜今度おすすめ教えて！", m: "happy" },
      ] },
      { gate: 30, text: "あかりとの会話、盛り上がってきた！もう少し好感度を上げると、デートに誘えそう。" },
      { her: "…あのさ、よかったら今度、直接会って話さない？ カフェとかで☕", m: "shy" },
      { me: "（デートのお誘いだ…！）ぜひ！行こう", },
      { scene: "cafe" },
      { sys: "── 週末、駅前のカフェ。あかりは少し緊張した様子で待っていた。" },
      { her: "きゃ、来てくれた…！ちゃんと会うと緊張するね。えっと、その…はい、これ私の書いたネットワーク構成図。見てほしくて", m: "shy" },
      { q: { q: "あかりの図でOSPFの1Gbpsリンクのコストは？(既定リファレンス100Mbps)", choices: ["1", "10", "100"], answer: 0, exp: "100/1000=0.1→最小コスト1に切り上げ。だからこそ帯域調整が要るの。" }, aff: 12 },
      { her: "…やっぱり君、分かってる人だ。一緒にいると安心する。", m: "love" },
      { gate: 70, text: "あかりの気持ちが高まっている。あと少し好感度を上げれば…？" },
      { her: "ねえ。…私たち、最適な経路(ルート)、見つけられたと思わない？ これからも…隣で一緒に、ネットワークの勉強してくれる？", m: "love" },
      { choice: [
        { t: "もちろん。君と一緒がいい", aff: 10, reply: "…っ、うん！うんっ！嬉しい…！これからよろしくね💕", m: "love" },
      ] },
      { end: "🎉 あかりと結ばれた！ 二人でCCNA合格を目指す毎日が始まった。ロンゲストマッチみたいに、一番ぴったりの相手を見つけたね。", m: "love" },
    ],
  },
  {
    id: "mio", name: "みお", age: 23, domain: "access",
    job: "インフラエンジニア", tagline: "みんなを繋ぐのが好き！",
    bio: "スイッチとWi-Fiが担当♪ VLANでみんなを整理整頓するのが快感。明るいって言われる！たくさん話そ〜📶",
    face: { skin: "#ffe3d0", hair: "#e88a4d", hair2: "#c96f38", eyes: "#7a9a3a", hairstyle: "twin", accessory: "clip", outfit: "#ff9f43" },
    theme: "#ff9f43",
    route: [
      { her: "やっほー！みおだよ😆 いいねくれてありがと！ノリで返しちゃった！", m: "happy" },
      { choice: [
        { t: "元気だね！話しやすそう", aff: 6, reply: "でしょ〜?? テンション高めでごめんね笑", m: "happy" },
        { t: "Wi-Fi担当ってかっこいい", aff: 6, reply: "えへへ、電波届けるの得意なの📡✨", m: "shy" },
      ] },
      { her: "ねえねえ、私スイッチの話になると止まらないの。ちょっと聞いていい？", m: "happy" },
      { q: { q: "802.1Qトランクで、タグを付けずに送られるVLANは？", choices: ["管理VLAN", "ネイティブVLAN", "音声VLAN"], answer: 1, exp: "ネイティブVLANはタグなし！両端で不一致だとVLANリークしちゃう⚠" }, aff: 12 },
      { her: "おお〜っ、正解！ちゃんと分かってる人、好きだな♪", m: "love" },
      { q: { q: "EtherChannelがLACPで成立する組み合わせは？(active/passive のうち)", choices: ["passive / passive", "active / passive", "どちらもNG"], answer: 1, exp: "片側activeならOK！passive同士は誰も交渉始めないからダメなの。" }, aff: 10 },
      { gate: 30, text: "みおとテンポよく盛り上がってる！もう少しで遊びに誘われそう。" },
      { her: "ねー！こんなに話合う人いないよ！ ねえ、今度みんな…じゃなくて、ふ、二人でご飯行かない?🍜", m: "shy" },
      { me: "行こう！みおとなら楽しそう", },
      { scene: "restaurant" },
      { sys: "── 賑やかなラーメン屋。みおは満面の笑みで手を振っている。" },
      { her: "こっちこっち〜！ここのラーメン最高なんだ。あ、そうだ、会社で困ってて…アクセスポートにPC繋いだのに通信できないの。なんでだと思う？", m: "normal" },
      { q: { q: "アクセスポートにPCを繋いだが通信不可。まず確認すべきは？", choices: ["ポートのVLAN割り当てとup/down", "OSPFのarea", "NATの設定"], answer: 0, exp: "アクセスポートは所属VLANとリンク状態(show vlan brief / show int)がまず基本！" }, aff: 12 },
      { her: "さっすが〜!! 頼りになる…//  ねえ、なんか、あなたといると自然体でいられる。", m: "love" },
      { gate: 70, text: "みおの笑顔がまぶしい。あと少し好感度を上げれば告白されそう…！" },
      { her: "あのね。私、いろんな人と繋がるの好きだけど…あなたとだけは、特別な回線でいたいなって。…わたしと、付き合ってくれる？", m: "love" },
      { choice: [
        { t: "こちらこそ！ずっと繋がっていよう", aff: 10, reply: "やった〜〜!! もう切れない専用リンクだね!!💕", m: "love" },
      ] },
      { end: "🎉 みおと結ばれた！ 毎日がにぎやかなトランクリンク。二人でたくさんのVLANを…じゃなくて、思い出を作っていこう。", m: "love" },
    ],
  },
  {
    id: "sena", name: "セナ", age: 27, domain: "security",
    job: "セキュリティエンジニア", tagline: "簡単には心、開かないから。",
    bio: "セキュリティ担当。ACLで不要な通信は全部denyします。人見知り。信頼できる人としか話しません。……一応、募集はしてる。",
    face: { skin: "#ffdcc8", hair: "#2a2a30", hair2: "#18181c", eyes: "#a23b4a", hairstyle: "pony", accessory: null, outfit: "#c0392b" },
    theme: "#c0392b",
    route: [
      { her: "……マッチしたから一応返す。セナ。言っておくけど、私、そう簡単には気を許さないから。", m: "annoyed" },
      { choice: [
        { t: "無理に開かなくていいよ、ゆっくりで", aff: 8, reply: "…っ。…そういうの、ずるい。ちょっとだけ、話してあげる。", m: "shy" },
        { t: "じゃあ信頼されるよう頑張るよ", aff: 6, reply: "ふーん。せいぜい頑張れば？(…悪くない)", m: "annoyed" },
      ] },
      { her: "私の仕事はネットワークを守ること。……あなた、最低限の知識はあるの？試させてもらう。", m: "normal" },
      { q: { q: "全ACLの末尾に暗黙的に存在するルールは？", choices: ["implicit permit any", "implicit deny any", "何もない"], answer: 1, exp: "末尾は暗黙のdeny any。permitを書かないと全部落ちる。……基本ね。" }, aff: 12 },
      { her: "……合格。少しは見直した。", m: "shy" },
      { q: { q: "DAI(Dynamic ARP Inspection)が照合する情報源は？", choices: ["MACアドレステーブル", "DHCPスヌーピングのバインディングDB", "ルーティングテーブル"], answer: 1, exp: "DHCPスヌーピングのバインディングと照合してARPスプーフィングを防ぐ。前提設定を忘れずに。" }, aff: 12 },
      { gate: 32, text: "セナの警戒が少しずつ解けてきた。信頼を積めば、心を開いてくれるかも。" },
      { her: "…あのね。あなたになら、少し話してもいいかなって。……その、直接会って。二人で。ご、ご飯とか。(顔真っ赤)", m: "shy" },
      { me: "喜んで。セナのおすすめの店で", },
      { scene: "night" },
      { sys: "── 夜景の見えるダイニング。いつも険しいセナが、今日は少しだけ柔らかい。" },
      { her: "……こんな風に誰かと来るの、久しぶり。実はね、会社でインシデントがあって。特定ホストだけ社内サーバへのHTTPを止めたいの。どのACL使う？", m: "normal" },
      { q: { q: "特定ホスト→サーバのHTTP(ポート80)だけを制御したい。使うべきACLは？", choices: ["標準ACL", "拡張ACL", "MAC ACL"], answer: 1, exp: "宛先+プロトコル+ポートで判断するには拡張ACL(100-199)。標準は送信元IPだけ。" }, aff: 12 },
      { her: "…完璧。あなたって、本当に信頼できる。……こんな気持ち、初めて。", m: "love" },
      { gate: 72, text: "セナの心の壁(ファイアウォール)が開きかけている。あと少し…！" },
      { her: "私、今まで誰も通さないようにしてきた。全部denyしてきた。……でも。あなただけは、permitしたいの。私のこと、もらってくれる…？", m: "love" },
      { choice: [
        { t: "もちろん。君の壁の内側にいさせて", aff: 10, reply: "……っ、ばか。…うん。あなただけ、特別に許可する。ずっとよ。💕", m: "love" },
      ] },
      { end: "🎉 セナと結ばれた！ 難攻不落だった彼女のホワイトリストに、あなたの名前が刻まれた。二人の通信は、これからも暗号化(SSH)で安全に。", m: "love" },
    ],
  },
  {
    id: "hikari", name: "ひかり", age: 24, domain: "fundamentals",
    job: "社内SE", tagline: "基礎から、ていねいに。",
    bio: "ネットワークの基礎を大事にしてます。OSI参照モデル、暗記より理解派。優しいって言われるのが密かな自慢です☺",
    face: { skin: "#ffe6d6", hair: "#a06a3a", hair2: "#7f5127", eyes: "#8a6a3a", hairstyle: "bob", accessory: null, outfit: "#38bdf8" },
    theme: "#38bdf8",
    route: [
      { her: "はじめまして、ひかりです☺ マッチできて嬉しいです。ゆっくりお話しできたらいいな。", m: "happy" },
      { choice: [
        { t: "落ち着く雰囲気だね", aff: 6, reply: "ふふ、よく言われます。あなたも話しやすい人ですね☺", m: "happy" },
        { t: "基礎を大事にするの、いいと思う", aff: 7, reply: "わ、分かってくれる人だ…！基礎って一番大切なんです✨", m: "love" },
      ] },
      { her: "せっかくなので、基礎の確認を一問だけ。気楽にどうぞ🌸", m: "normal" },
      { q: { q: "ルーティング(IPアドレスで経路制御)を行うOSI層は？", choices: ["第2層", "第3層", "第4層"], answer: 1, exp: "L3ネットワーク層です。L2はMACとスイッチング☺" }, aff: 12 },
      { her: "正解です！基礎がしっかりしてる方、素敵だと思います。", m: "happy" },
      { gate: 28, text: "ひかりと穏やかな時間。もう少し親しくなれば、お誘いできそう。" },
      { her: "あの…もしよければ、今度お茶でもいかがですか? 直接お話ししてみたくて☺", m: "shy" },
      { me: "ぜひ。楽しみにしてる", },
      { scene: "cafe" },
      { sys: "── 静かな喫茶店。ひかりはやわらかく微笑んでいる。" },
      { q: { q: "スイッチはコリジョンドメインを分割するが、分割しないものは?", choices: ["ブロードキャストドメイン", "VLAN", "MACテーブル"], answer: 0, exp: "スイッチはブロードキャストを全ポートへ。分割にはVLAN/ルータが必要です☺" }, aff: 12 },
      { her: "…あなたと話してると、基礎の大切さを思い出します。それに、すごく安心する。", m: "love" },
      { gate: 68, text: "ひかりの想いが芽生えている。あと少し好感度を上げれば…！" },
      { her: "私、派手なことは苦手だけど…あなたとなら、一歩ずつ、ていねいに関係を築いていける気がするんです。…私と、お付き合いしてもらえますか?", m: "love" },
      { choice: [
        { t: "こちらこそ。基礎から二人で積み上げよう", aff: 10, reply: "はい…!嬉しいです。ずっと、あなたの隣にいさせてください🌸💕", m: "love" },
      ] },
      { end: "🎉 ひかりと結ばれた！ OSI7層を下から積み上げるように、二人の信頼を一歩ずつ。土台のしっかりした、あたたかい関係。", m: "love" },
    ],
  },
  {
    id: "luna", name: "ルナ", age: 26, domain: "automation",
    job: "DevOps / NetOps", tagline: "手作業? 自動化しましょ。",
    bio: "ネットワーク自動化が専門。Ansibleとにらめっこの毎日。人間関係も宣言的に管理したい派。理想の状態に収束させましょ🤖",
    face: { skin: "#ffe0e8", hair: "#c9a0e8", hair2: "#a97fd0", eyes: "#7a5fd0", hairstyle: "wavy", accessory: "glasses", outfit: "#a855f7" },
    theme: "#a855f7",
    route: [
      { her: "こんばんは、ルナです🤖 マッチ確率、悪くなかったので返信を自動化…冗談です。あなたに興味があって。", m: "normal" },
      { choice: [
        { t: "自動化エンジニアってすごいね", aff: 6, reply: "ふふ、手作業は美しくないでしょ? 効率が愛です。", m: "happy" },
        { t: "宣言的に管理される恋、ちょっと憧れる", aff: 7, reply: "…あら。話が分かる人ね。好きよ、そういうの。", m: "love" },
      ] },
      { her: "テストさせて。あなたのスペックを確認したいの。", m: "normal" },
      { q: { q: "エージェントレス(SSH)でYAMLプレイブックを使う構成管理ツールは?", choices: ["Puppet", "Chef", "Ansible"], answer: 2, exp: "Ansibleはエージェントレス&プッシュ型。Puppet/Chefはエージェント型ね。" }, aff: 12 },
      { her: "正解。あなた、私のリポジトリにコミットする権限あげてもいいかも。", m: "happy" },
      { q: { q: "SDNで『サウスバウンド』APIが接続する相手は?", choices: ["業務アプリ", "ネットワーク機器(データプレーン)", "帯域外管理網"], answer: 1, exp: "サウスバウンドは機器へ指示を下ろす方向。ノースバウンドはアプリ向け(REST等)。" }, aff: 12 },
      { gate: 30, text: "ルナとの会話が理想の状態に収束してきた。もう少しで直接会えそう。" },
      { her: "会話のROI(投資対効果)が高いわ。…提案。今度、オフラインで会わない? デプロイは対面が確実でしょ。", m: "shy" },
      { me: "いいね、本番デプロイといこう", },
      { scene: "night" },
      { sys: "── モダンなバー。ルナはグラスを傾けながら、いつもより饒舌だ。" },
      { q: { q: "REST APIで『リソースの取得』に使うHTTPメソッドは?", choices: ["GET", "POST", "DELETE"], answer: 0, exp: "GET=取得。POST=作成、PUT/PATCH=更新、DELETE=削除。基本のCRUDね。" }, aff: 12 },
      { her: "…あなたといると、私の予測モデルが乱れるの。こんな変数、想定してなかった。", m: "love" },
      { gate: 70, text: "ルナの感情が想定外の値を示している。あと少し…！" },
      { her: "私、なんでも自動化してきた。でも、あなたへの気持ちだけは、手動でもいいから大事に処理したいの。…私のことを、あなたの構成管理下に置いてくれる?", m: "love" },
      { choice: [
        { t: "望むところ。理想の状態に、二人で収束しよう", aff: 10, reply: "…承認(approve)。あなたを本番環境にデプロイするわ。ずっと、ロールバックなしで。💕", m: "love" },
      ] },
      { end: "🎉 ルナと結ばれた！ 二人の関係は宣言的に定義され、いつも理想の状態(desired state)へ。冪等な愛が、これからも続いていく。", m: "love" },
    ],
  },
];

/* スワイプデッキのダミープロフィール(マッチしない/コミカル) */
const DECOYS = [
  { id: "d1", name: "ケンジ", age: 31, job: "自称ハッカー", bio: "俺のパスワードは password123。ポート全開で待ってるぜ🔓", face: { skin: "#f0d0b8", hair: "#222", hair2: "#111", eyes: "#333", hairstyle: "short", accessory: null, outfit: "#333" }, decoy: "セキュリティ意識が低すぎる…そっとスキップした。" },
  { id: "d2", name: "まりん", age: 22, job: "インフルエンサー", bio: "ネットワーク? 電波は繋がればOKでしょ〜✨ CCNAって美味しいの?", face: { skin: "#ffe0d0", hair: "#f2c14e", hair2: "#d9a72f", eyes: "#8a6a3a", hairstyle: "wavy", accessory: "star", outfit: "#ff6fa5" }, decoy: "話が全く噛み合わなそう…。今回は見送り。" },
  { id: "d3", name: "ボーグ", age: 40, job: "レガシー機器", bio: "拙者、Telnetでしか喋れぬ。暗号化? 何それ美味しいの。", face: { skin: "#cfc0b0", hair: "#888", hair2: "#666", eyes: "#556", hairstyle: "short", accessory: "glasses", outfit: "#607080" }, decoy: "平文通信は危険…SSHの時代だよ。スキップ。" },
];

const Love = {
  deck: [], route: null, hero: null, beatIdx: 0, playing: false,

  /* ---- ホーム: マッチ一覧 ---- */
  home() {
    const wrap = document.getElementById("love-matches");
    const matched = S.love.matched;
    if (!matched.length) {
      wrap.innerHTML = `<p class="lv-empty">まだマッチがありません。<br>「さがす」から気になる相手にいいねを送ろう！</p>`;
    } else {
      wrap.innerHTML = matched.map(id => {
        const h = HEROINES.find(x => x.id === id);
        const aff = S.love.aff[id] || 0;
        const done = S.love.done.includes(id);
        const hearts = "❤".repeat(Math.min(5, Math.ceil(aff / 20))) + "🤍".repeat(5 - Math.min(5, Math.ceil(aff / 20)));
        return `<div class="lv-match" onclick="Love.openChat('${id}')">
          <div class="lv-ava">${Art.face(h.face, done ? "love" : "happy")}</div>
          <div class="lv-info"><b>${h.name} <small>${h.age}</small></b>
            <div class="lv-hearts">${hearts} ${done ? "💑 恋人" : ""}</div>
            <div class="lv-last muted">${h.tagline}</div></div></div>`;
      }).join("");
    }
    go("love");
  },

  /* ---- スワイプ画面 ---- */
  openSwipe() {
    const seen = S.love.seen;
    const pool = [...HEROINES.filter(h => !seen.includes(h.id)), ...DECOYS.filter(d => !seen.includes(d.id))];
    this.deck = shuffle(pool);
    go("swipe");
    this.renderCard();
  },
  renderCard() {
    const wrap = document.getElementById("swipe-card");
    if (!this.deck.length) {
      wrap.innerHTML = `<div class="lv-nomore">今日はここまで！<br><button class="btn primary" onclick="Love.home()">メッセージへ</button></div>`;
      document.getElementById("swipe-actions").classList.add("hidden");
      return;
    }
    document.getElementById("swipe-actions").classList.remove("hidden");
    const c = this.deck[0];
    wrap.innerHTML = `<div class="profile-card">
      <div class="pc-photo" style="--pc:${c.theme || '#94a3b8'}">${Art.face(c.face, "normal")}</div>
      <div class="pc-body">
        <div class="pc-name">${c.name} <span>${c.age}</span></div>
        <div class="pc-job">💼 ${c.job}</div>
        <div class="pc-bio">${c.bio}</div>
        ${c.tagline ? `<div class="pc-tag">「${c.tagline}」</div>` : ""}
        <div class="pc-dist muted">📍 2.5km先</div>
      </div></div>`;
  },
  swipe(like) {
    const c = this.deck.shift();
    if (!c) return;
    S.love.seen.push(c.id);
    if (like && !c.decoy) {
      // ヒロイン → マッチ成立
      if (!S.love.matched.includes(c.id)) S.love.matched.push(c.id);
      S.love.aff[c.id] = S.love.aff[c.id] || 0;
      save();
      this.showMatch(c);
      return;
    } else if (like && c.decoy) {
      toast("いいねを送りました…返事はなさそう。");
    }
    save();
    this.renderCard();
  },
  showMatch(c) {
    const m = document.getElementById("match-modal");
    m.querySelector(".mm-face").innerHTML = Art.face(c.face, "happy");
    m.querySelector(".mm-name").textContent = `${c.name} とマッチ！`;
    m.classList.remove("hidden");
    m.querySelector(".mm-chat").onclick = () => { m.classList.add("hidden"); this.openChat(c.id); };
    m.querySelector(".mm-cont").onclick = () => { m.classList.add("hidden"); this.renderCard(); };
    if (S.love.matched.length === 1) unlock("first_match");
  },

  /* ---- チャット / ストーリー進行 ---- */
  openChat(id) {
    this.hero = HEROINES.find(x => x.id === id);
    this.route = this.hero.route;
    this.beatIdx = S.love.beat[id] || 0;
    document.getElementById("chat-name").textContent = this.hero.name;
    document.getElementById("chat-ava").innerHTML = Art.face(this.hero.face, "happy");
    document.getElementById("chat-log").innerHTML = "";
    document.getElementById("view-chat").style.setProperty("--theme", this.hero.theme);
    document.getElementById("chat-scene").className = "chat-scene";
    this.updateAff();
    go("chat");
    // これまでの流れを軽く復元(最後のヒロイン発言だけ表示)
    this.playing = true;
    this.step();
  },

  updateAff() {
    const aff = S.love.aff[this.hero.id] || 0;
    document.getElementById("chat-aff").style.width = Math.min(100, aff) + "%";
    document.getElementById("chat-affnum").textContent = Math.min(100, Math.round(aff));
  },

  bubble(side, text, mood) {
    const log = document.getElementById("chat-log");
    const row = document.createElement("div");
    row.className = "cbub " + side;
    if (side === "her") {
      row.innerHTML = `<div class="cbub-ava">${Art.face(this.hero.face, mood || "normal")}</div><div class="cbub-txt">${text}</div>`;
    } else {
      row.innerHTML = `<div class="cbub-txt">${text}</div>`;
    }
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  },
  narrate(text) {
    const log = document.getElementById("chat-log");
    const d = document.createElement("div");
    d.className = "cnarr"; d.textContent = text;
    log.appendChild(d); log.scrollTop = log.scrollHeight;
  },
  setScene(s) {
    document.getElementById("chat-scene").className = "chat-scene scene-" + s;
    // シーン切替時に大きめの立ち絵を表示
    const big = document.getElementById("chat-hero-big");
    big.innerHTML = Art.face(this.hero.face, "happy");
    big.classList.remove("hidden");
  },

  addAff(n) {
    const id = this.hero.id;
    S.love.aff[id] = Math.max(0, (S.love.aff[id] || 0) + n);
    save(); this.updateAff();
  },
  saveBeat() { S.love.beat[this.hero.id] = this.beatIdx; save(); },

  clearInput() { document.getElementById("chat-input").innerHTML = ""; },

  step() {
    this.clearInput();
    if (this.beatIdx >= this.route.length) return;
    const b = this.route[this.beatIdx];

    if (b.her !== undefined) { this.bubble("her", b.her, b.m); this.beatIdx++; this.saveBeat(); this.autoNext(); return; }
    if (b.me !== undefined)  { this.bubble("me", b.me); this.beatIdx++; this.saveBeat(); this.autoNext(); return; }
    if (b.sys !== undefined) { this.narrate(b.sys); this.beatIdx++; this.saveBeat(); this.autoNext(); return; }
    if (b.scene !== undefined) { this.setScene(b.scene); this.beatIdx++; this.saveBeat(); this.autoNext(); return; }

    if (b.choice) { this.renderChoices(b.choice); return; }
    if (b.q) { this.renderQuiz(b.q, b.aff || 10); return; }
    if (b.gate !== undefined) { this.renderGate(b); return; }
    if (b.end !== undefined) { this.renderEnd(b); return; }
  },
  autoNext() {
    // チャットらしく少し間をおいて次へ
    const b = this.route[this.beatIdx];
    if (!b) return;
    const interactive = b.choice || b.q || b.gate !== undefined || b.end !== undefined;
    setTimeout(() => this.step(), interactive ? 400 : 650);
  },

  renderChoices(opts) {
    const box = document.getElementById("chat-input");
    box.innerHTML = "";
    opts.forEach(o => {
      const btn = document.createElement("button");
      btn.className = "chat-choice";
      btn.textContent = o.t;
      btn.onclick = () => {
        [...box.querySelectorAll("button")].forEach(x => x.disabled = true);
        this.bubble("me", o.t);
        if (o.aff) this.addAff(o.aff);
        this.beatIdx++; this.saveBeat();
        if (o.reply) setTimeout(() => { this.bubble("her", o.reply, o.m); this.autoNext(); }, 500);
        else this.autoNext();
      };
      box.appendChild(btn);
    });
  },

  renderQuiz(q, affGain) {
    const box = document.getElementById("chat-input");
    box.innerHTML = `<div class="chat-quiz-q">💬 ${q.q}</div>`;
    const order = shuffle(q.choices.map((c, i) => i));
    order.forEach(i => {
      const btn = document.createElement("button");
      btn.className = "chat-choice quiz";
      btn.textContent = q.choices[i];
      btn.onclick = () => {
        [...box.querySelectorAll("button")].forEach(x => x.disabled = true);
        this.bubble("me", q.choices[i]);
        if (i === q.answer) {
          this.addAff(affGain);
          setTimeout(() => { this.bubble("her", `正解！ ${q.exp} 好感度+${affGain}💕`, "love"); this.beatIdx++; this.saveBeat(); this.autoNext(); }, 500);
        } else {
          this.addAff(-3);
          setTimeout(() => { this.bubble("her", `うーん、惜しい…。${q.exp}（好感度-3）でも一緒に覚えよ？`, "sad"); this.beatIdx++; this.saveBeat(); this.autoNext(); }, 500);
        }
      };
      box.appendChild(btn);
    });
  },

  renderGate(b) {
    const aff = S.love.aff[this.hero.id] || 0;
    if (aff >= b.gate) { this.beatIdx++; this.saveBeat(); this.step(); return; }
    this.narrate(b.text);
    const box = document.getElementById("chat-input");
    box.innerHTML = `<div class="chat-quiz-q">好感度 ${Math.round(aff)} / ${b.gate} … もう少し！${this.hero.name}の得意分野を復習して好感度を上げよう。</div>`;
    const btn = document.createElement("button");
    btn.className = "chat-choice";
    btn.textContent = `💘 ${domainName(this.hero.domain)}の復習クイズ(好感度アップ)`;
    btn.onclick = () => this.bonusQuiz();
    box.appendChild(btn);
  },
  bonusQuiz() {
    // ヒロインの分野から1問出し、正解で好感度アップ
    const pool = QUIZ_BANK.filter(x => x.domain === this.hero.domain && !Array.isArray(x.answer));
    const src = pool[Math.floor(Math.random() * pool.length)];
    const order = shuffle(src.choices.map((c, i) => i));
    const ansIdx = order.indexOf(src.answer);
    const box = document.getElementById("chat-input");
    box.innerHTML = `<div class="chat-quiz-q">💬 ${src.q}</div>`;
    order.forEach((oi, k) => {
      const btn = document.createElement("button");
      btn.className = "chat-choice quiz";
      btn.textContent = src.choices[oi];
      btn.onclick = () => {
        [...box.querySelectorAll("button")].forEach(x => x.disabled = true);
        this.bubble("me", src.choices[oi]);
        if (k === ansIdx) { this.addAff(10); setTimeout(() => { this.bubble("her", `正解！ ${src.exp} 好感度+10💕`, "love"); this.step(); }, 450); }
        else { setTimeout(() => { this.bubble("her", `惜しい…！ ${src.exp} もう一度どう？`, "normal"); this.step(); }, 450); }
      };
      box.appendChild(btn);
    });
  },

  renderEnd(b) {
    if (!S.love.done.includes(this.hero.id)) {
      S.love.done.push(this.hero.id);
      addXP(150);
      unlock("first_love");
      if (S.love.done.length >= HEROINES.length) unlock("harem");
    }
    save();
    this.bubble("her", "…", b.m);
    const big = document.getElementById("chat-hero-big");
    big.innerHTML = Art.face(this.hero.face, "love"); big.classList.remove("hidden");
    this.narrate(b.end);
    const box = document.getElementById("chat-input");
    box.innerHTML = "";
    const btn = document.createElement("button");
    btn.className = "chat-choice"; btn.textContent = "💐 エンディング (メッセージ一覧へ)";
    btn.onclick = () => { big.classList.add("hidden"); Love.home(); };
    box.appendChild(btn);
    document.getElementById("chat-scene").className = "chat-scene scene-ending";
  },
};
