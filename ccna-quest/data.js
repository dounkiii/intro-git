/* =====================================================================
 * CCNA Quest - 学習データ (問題バンク / フラッシュカード / ポート表)
 * CCNA 200-301 の出題領域に沿った日本語コンテンツ
 * すべてのデータはこのファイルに集約しています。
 * ===================================================================== */

/* 出題領域 (公式ブループリント v1.1 の比率) */
const CCNA_DOMAINS = [
  { id: "fundamentals", name: "ネットワーク基礎",       weight: 20, icon: "🌐", color: "#38bdf8" },
  { id: "access",       name: "ネットワークアクセス",     weight: 20, icon: "🔀", color: "#a78bfa" },
  { id: "connectivity", name: "IPコネクティビティ",       weight: 25, icon: "🧭", color: "#34d399" },
  { id: "services",     name: "IPサービス",             weight: 10, icon: "🛠️", color: "#fbbf24" },
  { id: "security",     name: "セキュリティ基礎",         weight: 15, icon: "🛡️", color: "#f87171" },
  { id: "automation",   name: "自動化・プログラマビリティ", weight: 10, icon: "🤖", color: "#f472b6" },
];

/* 難易度ラベル (1=初級 / 2=中級 / 3=本番レベル) */
const DIFF_LABELS = { 1: "初級", 2: "中級", 3: "本番" };

/* 試験の実情報 (模擬試験モードの説明に使用。合格ライン等は非公式値) */
const EXAM_FACTS = {
  code: "200-301",
  version: "v1.1 (2024年8月〜)",
  questionsReal: "本番は約100〜120問",
  minutesReal: 120,
  passNote: "合格ラインは非公開。歴史的に約825/1000(300〜1000スケール)と言われる目安",
  style: "リニア形式（前の問題には戻れない）。単一選択・複数選択・ドラッグ&ドロップ・シミュレーションあり",
};

/* 問題スキーマ補足:
 *   diff : 1|2|3 (難易度)
 *   answer : 正解index。複数選択のときは配列 [i,j]
 *   fig : 図解タイプ (Art.diagram に対応: topo_router / topo_lan / osi) 任意
 */

/* =====================================================================
 * クイズ問題バンク
 * q: 問題文 / choices: 選択肢 / answer: 正解index / exp: 解説 / domain: 領域id
 * ===================================================================== */
const QUIZ_BANK = [
  // ---- ネットワーク基礎 ----
  {
    domain: "fundamentals",
    q: "OSI参照モデルで、IPアドレスを使って経路制御(ルーティング)を行う層はどれ？",
    choices: ["第2層 データリンク層", "第3層 ネットワーク層", "第4層 トランスポート層", "第7層 アプリケーション層"],
    answer: 1,
    exp: "ルーティングとIPアドレスは第3層(ネットワーク層)。MACアドレスとスイッチングは第2層です。",
  },
  {
    domain: "fundamentals",
    q: "MACアドレスは何ビットで構成される？",
    choices: ["32ビット", "48ビット", "64ビット", "128ビット"],
    answer: 1,
    exp: "MACアドレスは48ビット(6バイト)。前半24bitがOUI(ベンダID)、後半24bitが個体識別です。",
  },
  {
    domain: "fundamentals",
    q: "TCPとUDPの違いとして正しいものは？",
    choices: [
      "TCPはコネクションレス、UDPはコネクション型",
      "TCPは再送制御あり、UDPはベストエフォート",
      "UDPは3ウェイハンドシェイクを行う",
      "TCPはヘッダが8バイトと軽量",
    ],
    answer: 1,
    exp: "TCPは3ウェイハンドシェイク・順序制御・再送で信頼性を確保。UDPはヘッダ8バイトで軽量・低遅延なベストエフォートです。",
  },
  {
    domain: "fundamentals",
    q: "IPv6アドレスは何ビット？",
    choices: ["32ビット", "48ビット", "64ビット", "128ビット"],
    answer: 3,
    exp: "IPv6は128ビット。16進数を4桁ずつ8ブロックで表記します(例: 2001:db8::1)。",
  },
  {
    domain: "fundamentals",
    q: "UTPケーブルでストレートではなくクロスケーブルが本来必要になる接続は？(Auto-MDIX無効時)",
    choices: ["PC ↔ スイッチ", "ルータ ↔ スイッチ", "スイッチ ↔ スイッチ", "PC ↔ ルータ(WAN)"],
    answer: 2,
    exp: "同種機器(スイッチ同士・PC同士・ルータ同士)はクロス、異種機器はストレートが基本。現代機器はAuto-MDIXで自動判別します。",
  },
  {
    domain: "fundamentals",
    q: "コリジョンドメインを分割するが、ブロードキャストドメインは分割しない機器は？",
    choices: ["リピータ(ハブ)", "スイッチ", "ルータ", "モデム"],
    answer: 1,
    exp: "スイッチはポートごとにコリジョンドメインを分割しますが、ブロードキャストは全ポートへ転送するため同一ブロードキャストドメインのままです。分割にはVLAN/ルータが必要。",
  },
  {
    domain: "fundamentals",
    q: "169.254.x.x のアドレスは何を意味する？",
    choices: ["ループバックアドレス", "APIPA (DHCP取得失敗の自動割当)", "マルチキャスト", "グローバルユニキャスト"],
    answer: 1,
    exp: "169.254.0.0/16 はAPIPA。DHCPサーバから応答が得られなかったときにOSが自動で割り当てるアドレスで、DHCP不達のサインです。",
  },

  // ---- ネットワークアクセス (スイッチング/VLAN/STP/無線) ----
  {
    domain: "access",
    q: "アクセスポートとトランクポートの違いとして正しいものは？",
    choices: [
      "アクセスは複数VLAN、トランクは単一VLAN",
      "トランクは複数VLANのフレームをタグ付き(802.1Q)で運ぶ",
      "アクセスポートはタグを付与する",
      "トランクはPCを直接接続する用途",
    ],
    answer: 1,
    exp: "トランクは802.1Qタグで複数VLANを1本のリンクに集約。アクセスポートは単一VLANに属し、通常はタグなしで端末を収容します。",
  },
  {
    domain: "access",
    q: "802.1Qトランクでタグを付けずに送信されるVLANを何と呼ぶ？",
    choices: ["管理VLAN", "ネイティブVLAN", "音声VLAN", "デフォルトVLAN"],
    answer: 1,
    exp: "ネイティブVLAN(既定はVLAN 1)のフレームはトランク上でタグなしで送られます。両端で不一致だとVLANリークの原因になります。",
  },
  {
    domain: "access",
    q: "STP(スパニングツリー)の主な目的は？",
    choices: [
      "帯域を増やす",
      "L2ループを防止する",
      "VLANを作成する",
      "IPアドレスを割り当てる",
    ],
    answer: 1,
    exp: "STPは冗長L2構成でブロードキャストストーム等のループを防ぐため、冗長経路を論理的にブロックします。",
  },
  {
    domain: "access",
    q: "STPでルートブリッジを決める基準は？",
    choices: ["最大のMACアドレス", "最小のブリッジID(優先度+MAC)", "最速のポート", "最も多いVLAN数"],
    answer: 1,
    exp: "ブリッジID = 優先度(既定32768) + MACアドレス。この値が最小のスイッチがルートブリッジになります。優先度を下げて任意に指定できます。",
  },
  {
    domain: "access",
    q: "PortFastを設定する適切なポートは？",
    choices: ["スイッチ間トランク", "ルータ接続ポート", "エンドデバイス(PC)接続のアクセスポート", "STPルートポート"],
    answer: 2,
    exp: "PortFastはリスニング/ラーニングを飛ばして即forwardingにします。ループのないエンド端末ポート専用。スイッチ間で使うとループの危険があります。",
  },
  {
    domain: "access",
    q: "複数の物理リンクを1本の論理リンクに束ねて帯域と冗長性を得る技術は？",
    choices: ["VLAN", "EtherChannel (LAG)", "STP", "HSRP"],
    answer: 1,
    exp: "EtherChannel(LACP/PAgP)は複数リンクを論理集約。帯域増加とリンク冗長を実現し、STPは束ねた1本として扱います。",
  },
  {
    domain: "access",
    q: "無線LANでAPを集中管理し設定を配布するコントローラを何という？",
    choices: ["WLC (Wireless LAN Controller)", "AAA", "RADIUS", "SSID"],
    answer: 0,
    exp: "WLCはLightweight AP(LWAP)をCAPWAPで集中管理します。SSIDはネットワーク名、RADIUSは認証サーバです。",
  },

  // ---- IPコネクティビティ (ルーティング) ----
  {
    domain: "connectivity",
    q: "ルーティングテーブルで最も優先される(信頼される)経路の指標は？",
    choices: ["最大のメトリック", "最長プレフィックスマッチ", "最小のホップ数のみ", "最古の経路"],
    answer: 1,
    exp: "宛先選択はまずロンゲストマッチ(最長一致)。同じプレフィックス長ならAD(アドミニストレイティブディスタンス)、次にメトリックで選ばれます。",
  },
  {
    domain: "connectivity",
    q: "スタティックルートのアドミニストレイティブディスタンス(AD)は既定でいくつ？",
    choices: ["0", "1", "90", "110"],
    answer: 1,
    exp: "直接接続=0、スタティック=1、EIGRP=90、OSPF=110、RIP=120。ADが小さいほど信頼され優先されます。",
  },
  {
    domain: "connectivity",
    q: "OSPFのアドミニストレイティブディスタンスは？",
    choices: ["90", "100", "110", "120"],
    answer: 2,
    exp: "OSPF=110。リンクステート型でコスト(帯域ベース)をメトリックに使います。EIGRP=90、RIP=120。",
  },
  {
    domain: "connectivity",
    q: "デフォルトルートの表記として正しいものは？",
    choices: ["0.0.0.0/0", "255.255.255.255/32", "127.0.0.1/8", "224.0.0.0/4"],
    answer: 0,
    exp: "0.0.0.0/0 は全宛先にマッチする最短プレフィックス。より具体的な経路がない場合の最後の手段(gateway of last resort)です。",
  },
  {
    domain: "connectivity",
    q: "OSPFで隣接関係(ネイバー)を確立する際に一致している必要がないものは？",
    choices: ["Helloインターバル", "エリアID", "サブネット", "ルータID"],
    answer: 3,
    exp: "Hello/Deadタイマー・エリアID・サブネット・認証・MTUなどは一致が必要。ルータIDはむしろ一意である必要があります(重複は不可)。",
  },
  {
    domain: "connectivity",
    q: "OSPFのメトリック(コスト)の既定の計算基準は？",
    choices: ["ホップ数", "遅延", "帯域幅 (10^8 / 帯域bps)", "負荷"],
    answer: 2,
    exp: "OSPFコスト = リファレンス帯域(既定10^8=100Mbps) ÷ インタフェース帯域。高速リンクほど低コスト=優先されます。",
  },
  {
    domain: "connectivity",
    q: "同一サブネット内で仮想IP/仮想MACを使いデフォルトゲートウェイを冗長化するCisco独自プロトコルは？",
    choices: ["OSPF", "HSRP", "STP", "DHCP"],
    answer: 1,
    exp: "HSRP(FHRP)はアクティブ/スタンバイ構成で仮想ゲートウェイを提供。障害時に自動フェイルオーバーします。標準はVRRP、負荷分散はGLBP。",
  },
  {
    domain: "connectivity",
    q: "IPv6のリンクローカルアドレスのプレフィックスは？",
    choices: ["2000::/3", "FE80::/10", "FF00::/8", "::1/128"],
    answer: 1,
    exp: "FE80::/10 がリンクローカル。同一リンク内でのみ有効で、ルータを越えません。FF00::/8はマルチキャスト、::1はループバック。",
  },

  // ---- IPサービス ----
  {
    domain: "services",
    q: "プライベートIPをグローバルIPに変換し、多数の端末で1つのグローバルIPを共有する技術は？",
    choices: ["Static NAT", "PAT (NAT Overload)", "DNS", "DHCP"],
    answer: 1,
    exp: "PAT(NAPT/NATオーバーロード)はポート番号で複数セッションを識別し、1つのグローバルIPを多端末で共有します。家庭用ルータの動作です。",
  },
  {
    domain: "services",
    q: "DHCPでクライアントがIPを取得する正しい順序は？",
    choices: [
      "Offer → Discover → Request → Ack",
      "Discover → Offer → Request → Ack",
      "Request → Ack → Discover → Offer",
      "Discover → Request → Offer → Ack",
    ],
    answer: 1,
    exp: "DORA: Discover(探索)→Offer(提示)→Request(要求)→Ack(確認)。最初のDiscoverはブロードキャストで送信されます。",
  },
  {
    domain: "services",
    q: "ネットワーク機器の時刻を同期させ、ログの相関やSSL等の整合を保つプロトコルは？",
    choices: ["SNMP", "NTP", "Syslog", "FTP"],
    answer: 1,
    exp: "NTP(UDP 123)は時刻同期プロトコル。ログのタイムスタンプ整合や証明書検証に重要です。Stratumで階層を表します。",
  },
  {
    domain: "services",
    q: "Syslogの重大度(Severity)で最も緊急度が高いのは？",
    choices: ["0 Emergency", "3 Error", "6 Informational", "7 Debug"],
    answer: 0,
    exp: "0=Emergency(最重大)〜7=Debug(最詳細)。数字が小さいほど深刻。覚え方: 'Every Awesome Cisco Engineer Will Need Ice cream Daily'。",
  },
  {
    domain: "services",
    q: "SNMPで、機器側から管理サーバへ異常発生を自発的に通知するメッセージは？",
    choices: ["Get", "Set", "Trap", "Walk"],
    answer: 2,
    exp: "Trap(およびInform)は監視対象(エージェント)からNMSへの非同期通知。Get/Setはポーリング型の取得・設定です。",
  },

  // ---- セキュリティ基礎 ----
  {
    domain: "security",
    q: "スイッチのポートに接続できるMACアドレスを制限する機能は？",
    choices: ["DHCP Snooping", "Port Security", "802.1X", "ACL"],
    answer: 1,
    exp: "Port SecurityはポートごとにMACアドレス数や特定MACを制限し、違反時にshutdown等のアクションを取ります。",
  },
  {
    domain: "security",
    q: "標準ACL(Standard ACL)がフィルタリングの判断に使えるのは？",
    choices: ["送信元IPのみ", "送信元と宛先IP+ポート", "MACアドレス", "VLAN ID"],
    answer: 0,
    exp: "標準ACL(1-99)は送信元IPのみで判定。宛先やポート・プロトコルで細かく制御するには拡張ACL(100-199)が必要です。",
  },
  {
    domain: "security",
    q: "ACLの各行の最後に暗黙的に存在するルールは？",
    choices: ["implicit permit any", "implicit deny any", "log all", "何もない"],
    answer: 1,
    exp: "全ACLの末尾には暗黙のdeny anyがあります。少なくとも1つのpermitを書かないと全通信が拒否されます。",
  },
  {
    domain: "security",
    q: "不正なDHCPサーバからの応答をブロックし信頼ポートのみ許可する機能は？",
    choices: ["Port Security", "DHCP Snooping", "STP", "NAT"],
    answer: 1,
    exp: "DHCP Snoopingは信頼(trusted)ポート以外からのDHCP Offer/Ackを破棄し、なりすましDHCPサーバを防ぎます。DAIやIPSGの前提にもなります。",
  },
  {
    domain: "security",
    q: "AAAの3つのAが指すものは？",
    choices: [
      "Access, Audit, Alert",
      "Authentication, Authorization, Accounting",
      "Address, Area, Access",
      "Availability, Anonymity, Auditing",
    ],
    answer: 1,
    exp: "認証(誰か)・認可(何ができるか)・アカウンティング(何をしたか)。RADIUS/TACACS+サーバと連携して集中管理します。",
  },
  {
    domain: "security",
    q: "リモート管理でTelnetよりSSHが推奨される最大の理由は？",
    choices: ["高速だから", "通信が暗号化されるから", "設定が簡単だから", "ポート番号が小さいから"],
    answer: 1,
    exp: "Telnet(TCP23)は平文でパスワードも丸見え。SSH(TCP22)は暗号化されるため、リモート管理はSSH v2を使うのが原則です。",
  },

  // ---- 自動化・プログラマビリティ ----
  {
    domain: "automation",
    q: "人にも機械にも読みやすく、キー:値やリストで構成される、Ansible等でよく使われるデータ形式は？",
    choices: ["JSON", "YAML", "XML", "CSV"],
    answer: 1,
    exp: "YAMLはインデントで階層を表す設定向けフォーマット。JSONはAPI応答で多用、XMLはNETCONFで使われます。",
  },
  {
    domain: "automation",
    q: "REST APIで「リソースの取得」に使うHTTPメソッドは？",
    choices: ["GET", "POST", "DELETE", "PUT"],
    answer: 0,
    exp: "GET=取得、POST=作成、PUT/PATCH=更新、DELETE=削除。RESTはHTTP動詞でCRUDを表現します。",
  },
  {
    domain: "automation",
    q: "従来のネットワークで、各機器が自分で経路判断を行う『分散した知能』の部分を何と呼ぶ？",
    choices: ["データプレーン", "コントロールプレーン", "マネジメントプレーン", "サービスプレーン"],
    answer: 1,
    exp: "経路計算などの判断がコントロールプレーン、実際の転送がデータプレーン。SDNはコントロールプレーンを集中コントローラに分離します。",
  },
  {
    domain: "automation",
    q: "設定を『あるべき状態』として宣言し、差分を自動で適用する構成管理の考え方は？",
    choices: ["命令的(Imperative)", "宣言的(Declarative)", "手続き的スクリプト", "対話的CLI"],
    answer: 1,
    exp: "宣言的モデルは『最終状態』を記述し、ツール(Ansible/Terraform等)が差分を埋めます。CCNAではIaC/コントローラの文脈で問われます。",
  },
  {
    domain: "automation",
    q: "REST APIの応答で「200」が意味するものは？",
    choices: ["リダイレクト", "成功(OK)", "クライアントエラー", "サーバエラー"],
    answer: 1,
    exp: "2xx=成功、3xx=リダイレクト、4xx=クライアントエラー(401認証失敗/404未検出)、5xx=サーバエラー。",
  },
];

/* ---- 既存問題は基礎レベル(初級)として難易度を付与 ---- */
QUIZ_BANK.forEach(q => { if (!q.diff) q.diff = 1; });

/* =====================================================================
 * 追加問題バンク (中級〜本番レベル / 一部は複数選択・図解つき)
 * answer が配列のものは「2つ選べ」形式。
 * ===================================================================== */
QUIZ_BANK.push(
  // ---- 基礎 (中級〜本番) ----
  { domain: "fundamentals", diff: 1,
    q: "/27 のサブネットで利用可能なホストアドレス数は？",
    choices: ["30", "32", "62", "14"], answer: 0,
    exp: "/27 はホストビット5 → 2^5=32アドレス。ネットワークとブロードキャストを除き 30 台が利用可能です。" },
  { domain: "fundamentals", diff: 2,
    q: "ホストに 192.168.10.100/26 が設定されている。所属するネットワークアドレスは？",
    choices: ["192.168.10.0", "192.168.10.64", "192.168.10.96", "192.168.10.128"], answer: 1,
    exp: "/26 はマスク255.255.255.192、ブロックサイズ64。.100 は 64〜127 の範囲なのでネットワークは .64(ブロードキャスト .127)です。" },
  { domain: "fundamentals", diff: 3,
    q: "【2つ選べ】UDPについて正しい記述はどれか？",
    choices: ["3ウェイハンドシェイクでセッションを確立する", "コネクションレスでベストエフォート配送", "TCPよりヘッダオーバーヘッドが小さい", "順序制御を保証する"],
    answer: [1, 2],
    exp: "UDPはコネクションレス(ハンドシェイクなし)、ヘッダは8バイトでTCP(20バイト以上)より軽量。順序保証・再送はありません。" },
  { domain: "fundamentals", diff: 3, fig: "topo_lan",
    q: "アクセススイッチのポートで show interfaces を見ると input errors・CRC errors・runts が増え続けている。最も疑わしい原因は？",
    choices: ["ホストのデフォルトゲートウェイ誤設定", "デュプレックス不一致またはケーブル不良", "DNSサーバの誤設定", "アウトバウンドACLの破棄"],
    answer: 1,
    exp: "CRC・runts・late collision は典型的なL1/L2の症状で、デュプレックス不一致やケーブル不良が原因。L3/名前解決/ACLの問題ではこれらのカウンタは増えません。" },

  // ---- ネットワークアクセス ----
  { domain: "access", diff: 2,
    q: "RSTPで、同一セグメント上の指定ポートのバックアップとなるポートロールは？",
    choices: ["ルートポート", "指定ポート", "代替(Alternate)ポート", "バックアップ(Backup)ポート"], answer: 3,
    exp: "Backupポートは同一セグメント上の指定ポートのバックアップ。Alternateポートはルートへの代替経路のバックアップです。" },
  { domain: "access", diff: 3,
    q: "【2つ選べ】EtherChannelがLACPで正しく形成される組み合わせはどれか？",
    choices: ["active / active", "active / passive", "passive / passive", "on / active"],
    answer: [0, 1],
    exp: "少なくとも片側がactiveならネゴシエーション成立。passive同士は誰も交渉を始めず不成立。onはネゴシエーションなしでactive/passiveとは組めません。" },
  { domain: "access", diff: 3,
    q: "SW-AのポートチャネルがモードON、SW-BがLACP activeのとき結果は？",
    choices: ["LACPでチャネルが形成される", "PAgPで形成される", "EtherChannelは形成されない", "形成されるがsuspend状態"],
    answer: 2,
    exp: "ON はネゴシエーションを一切行わず、相手もONの時だけ束ねます。active/passiveと混在するとチャネルは形成されません。" },
  { domain: "access", diff: 2,
    q: "Lightweight AP がWLCへ制御/データトラフィックをトンネルするために使うプロトコルは？",
    choices: ["LWAPPのみ", "CAPWAP", "GRE", "Telnet"], answer: 1,
    exp: "CAPWAP(Control And Provisioning of Wireless Access Points)がLightweight APとWLC間の標準トンネルです。" },
  { domain: "access", diff: 2, fig: "topo_lan",
    q: "Router-on-a-Stick(1本のトランクで複数VLANをルーティング)で、各サブインタフェースに必要な設定は？",
    choices: ["switchport mode trunk", "encapsulation dot1q <VLAN-ID> とIPアドレス", "no ip routing", "VLANごとに物理ケーブルを追加"], answer: 1,
    exp: "各サブインタフェースに、対応VLANの802.1Qタグ(encapsulation dot1q)と、そのVLANのゲートウェイとなるIPアドレスを設定します。" },

  // ---- IPコネクティビティ ----
  { domain: "connectivity", diff: 2,
    q: "同じ宛先プレフィックスをスタティック(AD1)・OSPF(AD110)・EIGRP(AD90)で学習した。ルーティングテーブルに載るのは？",
    choices: ["OSPF", "EIGRP", "スタティック", "3つとも負荷分散"], answer: 2,
    exp: "プレフィックス長が同じ場合はADが最小の経路が選ばれます。スタティック(AD1)が最優先です。" },
  { domain: "connectivity", diff: 2,
    q: "ルーティングテーブルに 10.1.1.0/24・10.1.0.0/16・0.0.0.0/0 がある。宛先 10.1.1.5 はどれで転送される？",
    choices: ["10.1.1.0/24", "10.1.0.0/16", "0.0.0.0/0", "破棄される"], answer: 0,
    exp: "AD/メトリックより先にロンゲストマッチ(最長一致)が優先。/24 が最も具体的なので選ばれます。" },
  { domain: "connectivity", diff: 3, fig: "topo_router",
    q: "【2つ選べ】イーサネットリンクで2台のOSPFv2ルータが隣接を確立するために一致が必要なものは？",
    choices: ["Hello/Deadタイマー", "エリアID", "ルータID", "OSPFプロセスID"],
    answer: [0, 1],
    exp: "タイマー・エリアID・サブネット/マスク・MTU・認証は一致が必要。ルータIDは逆に一意である必要があり、プロセスIDはローカルな意味しかありません。" },
  { domain: "connectivity", diff: 3,
    q: "マルチアクセスのイーサネットに優先度1,1,0(ルータID 1.1.1.1/2.2.2.2/3.3.3.3)のOSPFルータがある。DRになるのは？",
    choices: ["RID 1.1.1.1", "RID 2.2.2.2", "RID 3.3.3.3", "DRは選出されない"], answer: 1,
    exp: "優先度が最高のルータが勝ち、優先度0は選出対象外。優先度1が2台あるので、ルータIDが大きい 2.2.2.2 がDRになります。" },
  { domain: "connectivity", diff: 2,
    q: "OSPFの既定リファレンス帯域(100Mbps)で、1Gbpsインタフェースのコストは？",
    choices: ["1", "10", "100", "64"], answer: 0,
    exp: "コスト = 100Mbps / 1000Mbps = 0.1 → 最小コスト1に切り上げ。高速リンクを区別するにはreference-bandwidthの調整が必要です。" },
  { domain: "connectivity", diff: 1,
    q: "フローティングスタティックルート(バックアップ経路)はどう設定する？",
    choices: ["メトリックを下げる", "ADを高く設定する", "ADを低く設定する", "帯域を上げる"], answer: 1,
    exp: "フローティングスタティックはADを高く設定し、主経路(低AD)が消えたときだけルーティングテーブルに入るバックアップです。" },
  { domain: "connectivity", diff: 3,
    q: "IPv4のHSRPについて正しい記述は？",
    choices: ["優先度が最も低いルータがActiveになる", "優先度(既定100)が最高、同値ならIPが大きい方がActive", "既定で両ルータが同時に転送する", "仮想MACは 0000.5E00.01xx"],
    answer: 1,
    exp: "優先度最高(既定100)、同値なら最大IPがActiveで、Activeのみ転送します。0000.5E00.01xx はVRRPの仮想MAC(HSRPv1は0000.0C07.ACxx)。" },
  { domain: "connectivity", diff: 2,
    q: "IPv6のデフォルトルートを表す構文は？",
    choices: ["ip route 0.0.0.0 0.0.0.0 <nh>", "ipv6 route ::/0 <nh>", "ipv6 route ::1/128 <nh>", "ipv6 route FE80::/10 <nh>"], answer: 1,
    exp: "::/0 が全宛先にマッチするIPv6デフォルトルート。::1/128はループバック、FE80::/10はリンクローカルです。" },

  // ---- IPサービス ----
  { domain: "services", diff: 2,
    q: "NTPのstratum(ストラタム)値が示すものは？",
    choices: ["時刻更新の暗号強度", "基準クロックからのホップ数(階層)", "ポーリング間隔(秒)", "UTCからのタイムゾーン差"], answer: 1,
    exp: "stratumは基準クロックからの距離。stratum0=基準源、1=直結、以降ホップごとに+1。数字が小さいほど正確です。" },
  { domain: "services", diff: 2,
    q: "管理トラフィックの認証と暗号化の両方に対応するSNMPのバージョンは？",
    choices: ["SNMPv1", "SNMPv2c", "SNMPv3", "SNMPv2"], answer: 2,
    exp: "認証+暗号化(authPriv)はSNMPv3のみ。v1/v2cは平文のコミュニティストリングに依存します。" },
  { domain: "services", diff: 2,
    q: "QoSでレイヤ3(IPヘッダ)のトラフィック優先度をマークするフィールドは？",
    choices: ["CoS", "DSCP", "MPLS EXP", "802.1p"], answer: 1,
    exp: "DSCPはIPv4のToSバイト内6ビット(L3)。CoS/802.1pは802.1Qタグ内のL2マーキングです。" },

  // ---- セキュリティ ----
  { domain: "security", diff: 3,
    q: "ベストプラクティス上、標準ACLはどこに配置すべき？",
    choices: ["送信元にできるだけ近く", "宛先にできるだけ近く", "最も負荷の低いルータ", "経路上の全インタフェース"], answer: 1,
    exp: "標準ACLは送信元IPしか見ないため、宛先の近くに置かないと他ネットワーク宛ての通信まで巻き込んで遮断してしまいます。拡張ACLは送信元近くに配置。" },
  { domain: "security", diff: 3,
    q: "【2つ選べ】TACACS+について正しい記述はどれか？",
    choices: ["パケット内のパスワードのみ暗号化する", "パケット本体全体を暗号化する", "認証・認可・アカウンティングを分離できる", "UDPを使用する"],
    answer: [1, 2],
    exp: "TACACS+はCisco独自・TCP/49・ペイロード全体を暗号化し、AAAを分離できるため機器管理に最適。RADIUSはパスワードのみ暗号化しauthN/authZを結合します。" },
  { domain: "security", diff: 3,
    q: "Dynamic ARP Inspection(DAI)はARPパケットを何と照合して検証する？",
    choices: ["スイッチのMACアドレステーブル", "DHCPスヌーピングのバインディングDB", "ローカルARPキャッシュ", "ルーティングテーブル"], answer: 1,
    exp: "DAIはDHCPスヌーピングのIP-MACバインディング表と照合するため、先にDHCPスヌーピングが必要。ARPスプーフィング(中間者攻撃)を防ぎます。" },
  { domain: "security", diff: 2,
    q: "WPA3-Personalが、オフライン辞書攻撃対策としてWPA2のPSKハンドシェイクを置き換えた仕組みは？",
    choices: ["TKIP", "SAE (Simultaneous Authentication of Equals)", "WEP", "EAP-TLS"], answer: 1,
    exp: "WPA3-PersonalはSAE(Dragonfly)で4ウェイPSKハンドシェイクを置換。WPA2の暗号はAES-CCMP、EAP-TLSは802.1Xのエンタープライズ方式です。" },

  // ---- 自動化 ----
  { domain: "automation", diff: 2,
    q: "エージェントレス(SSH利用)で、YAMLのプレイブックで自動化を定義する構成管理ツールは？",
    choices: ["Puppet", "Chef", "Ansible", "SaltStack"], answer: 2,
    exp: "Ansibleはエージェントレスかつプッシュ型でYAMLプレイブックを使用。Puppet/Chefはエージェント型・プル型です。" },
  { domain: "automation", diff: 3,
    q: "SDNアーキテクチャで『サウスバウンド』インタフェースがコントローラと接続する相手は？",
    choices: ["業務アプリケーション", "ネットワーク機器(データプレーン)", "ノースバウンドREST API", "帯域外管理ネットワーク"], answer: 1,
    exp: "サウスバウンドAPI(OpenFlow/NETCONF等)は機器へ指示を下ろす方向。ノースバウンドAPI(通常REST)はアプリ(DNA/Catalyst Center等)へ上向きに公開します。" },
);

/* =====================================================================
 * フラッシュカード (用語 → 意味)
 * ===================================================================== */
const FLASHCARDS = [
  { domain: "fundamentals", front: "OSI参照モデル 7層", back: "物理→データリンク→ネットワーク→トランスポート→セッション→プレゼンテーション→アプリケーション。覚え方『アプセトネデブ』を下から。" },
  { domain: "fundamentals", front: "TCP/IP 4層モデル", back: "ネットワークインタフェース / インターネット / トランスポート / アプリケーション。" },
  { domain: "fundamentals", front: "ブロードキャストドメイン", back: "ブロードキャストが届く範囲。ルータ/VLAN境界で分割される。" },
  { domain: "fundamentals", front: "MTU", back: "1フレームで送れる最大ペイロードサイズ。イーサネット既定は1500バイト。" },
  { domain: "access",       front: "VLAN", back: "1台の物理スイッチを論理的に複数のブロードキャストドメインに分割する仕組み。" },
  { domain: "access",       front: "802.1Q", back: "VLANタグの標準規格。フレームに4バイトのタグ(VLAN ID等)を挿入する。" },
  { domain: "access",       front: "STPのポート状態", back: "Blocking→Listening→Learning→Forwarding(RSTPではDiscarding/Learning/Forwarding)。" },
  { domain: "access",       front: "CDP / LLDP", back: "隣接機器を検出するプロトコル。CDPはCisco独自、LLDP(802.1AB)は業界標準。" },
  { domain: "connectivity", front: "AD(アドミニストレイティブディスタンス)", back: "経路情報源の信頼度。接続0/静的1/EIGRP90/OSPF110/RIP120。小さいほど優先。" },
  { domain: "connectivity", front: "ロンゲストマッチ", back: "複数経路が該当する場合、最も長い(詳細な)サブネットマスクの経路を選ぶ原則。" },
  { domain: "connectivity", front: "FHRP", back: "First Hop Redundancy Protocol。HSRP/VRRP/GLBPでデフォルトGWを冗長化。" },
  { domain: "connectivity", front: "EIGRP", back: "Cisco準拠のハイブリッド型。DUALアルゴリズム、メトリックは帯域と遅延ベース。AD=90。" },
  { domain: "services",     front: "DHCP DORA", back: "Discover→Offer→Request→Acknowledge の4ステップでIP設定を配布。" },
  { domain: "services",     front: "NAT / PAT", back: "NATはIP変換。PAT(オーバーロード)はポートで多重化し1グローバルIPを共有。" },
  { domain: "services",     front: "QoS", back: "遅延に弱い音声/映像を優先制御。分類・マーキング・キューイング・シェーピング。" },
  { domain: "security",     front: "CIAトライアド", back: "機密性(Confidentiality)・完全性(Integrity)・可用性(Availability)。セキュリティの3本柱。" },
  { domain: "security",     front: "拡張ACL 番号範囲", back: "標準ACL=1-99 / 1300-1999、拡張ACL=100-199 / 2000-2699。" },
  { domain: "security",     front: "WPA2 / WPA3", back: "無線暗号化。WPA2はAES(CCMP)、WPA3はSAEでより強固。WEP/WPAは非推奨。" },
  { domain: "automation",   front: "SDN", back: "Software Defined Networking。コントロールプレーンを集中コントローラに分離し、APIで制御。" },
  { domain: "automation",   front: "Puppet / Chef / Ansible", back: "構成管理ツール。AnsibleはエージェントレスでSSH/YAMLを使う点が特徴。" },
];

/* =====================================================================
 * ポート & プロトコル (マッチングゲーム用)
 * ===================================================================== */
const PORTS = [
  { proto: "FTP (データ/制御)", port: "20 / 21", layer: "TCP" },
  { proto: "SSH", port: "22", layer: "TCP" },
  { proto: "Telnet", port: "23", layer: "TCP" },
  { proto: "SMTP", port: "25", layer: "TCP" },
  { proto: "DNS", port: "53", layer: "TCP/UDP" },
  { proto: "DHCP (サーバ/クライアント)", port: "67 / 68", layer: "UDP" },
  { proto: "TFTP", port: "69", layer: "UDP" },
  { proto: "HTTP", port: "80", layer: "TCP" },
  { proto: "HTTPS", port: "443", layer: "TCP" },
  { proto: "NTP", port: "123", layer: "UDP" },
  { proto: "SNMP", port: "161 / 162", layer: "UDP" },
  { proto: "Syslog", port: "514", layer: "UDP" },
  { proto: "RADIUS (認証/課金)", port: "1812 / 1813", layer: "UDP" },
];

/* =====================================================================
 * 実績(バッジ) 定義
 * ===================================================================== */
const ACHIEVEMENTS = [
  { id: "first_quiz",   name: "はじめの一歩",     desc: "初めてクイズをクリア",           icon: "🎯" },
  { id: "combo10",      name: "コンボマスター",   desc: "10連続正解を達成",             icon: "🔥" },
  { id: "perfect",      name: "パーフェクト",     desc: "クイズを全問正解でクリア",        icon: "💯" },
  { id: "subnet25",     name: "サブネットの達人", desc: "サブネット道場で25問正解",       icon: "🧮" },
  { id: "streak3",      name: "習慣の芽",         desc: "3日連続でログイン学習",          icon: "🌱" },
  { id: "level5",       name: "ネットワーカー",   desc: "レベル5に到達",               icon: "⭐" },
  { id: "level10",      name: "CCNA候補生",       desc: "レベル10に到達",              icon: "🏅" },
  { id: "all_domains",  name: "全領域制覇",       desc: "全6領域のクイズを各1回クリア",   icon: "🌈" },
  { id: "flash_all",    name: "暗記王",           desc: "全フラッシュカードを確認",       icon: "🃏" },
  { id: "ports_perfect",name: "ポートの番人",     desc: "ポートゲームを全問正解",          icon: "🚪" },
  { id: "adv_clear",    name: "ネット王国の勇者", desc: "アドベンチャーを全章クリア",      icon: "🗺️" },
  { id: "exam_pass",    name: "模擬試験 合格",     desc: "模擬試験で合格ライン到達",        icon: "📜" },
  { id: "rush30",       name: "スピードの申し子", desc: "サブネット・ラッシュで30問正解",  icon: "⚡" },
  { id: "cli_first",    name: "コマンド入門",     desc: "コマンド道場を初クリア",          icon: "⌨️" },
  { id: "cli_master",   name: "IOSマスター",      desc: "全コマンドシナリオをクリア",      icon: "🛠️" },
];
