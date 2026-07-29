/* =====================================================================
 * CCNA Quest - 学習データ (問題バンク / フラッシュカード / ポート表)
 * CCNA 200-301 の出題領域に沿った日本語コンテンツ
 * すべてのデータはこのファイルに集約しています。
 * ===================================================================== */

/* 出題領域 (公式ブループリントの比率) */
const CCNA_DOMAINS = [
  { id: "fundamentals", name: "ネットワーク基礎",       weight: 20, icon: "🌐", color: "#38bdf8" },
  { id: "access",       name: "ネットワークアクセス",     weight: 20, icon: "🔀", color: "#a78bfa" },
  { id: "connectivity", name: "IPコネクティビティ",       weight: 25, icon: "🧭", color: "#34d399" },
  { id: "services",     name: "IPサービス",             weight: 10, icon: "🛠️", color: "#fbbf24" },
  { id: "security",     name: "セキュリティ基礎",         weight: 15, icon: "🛡️", color: "#f87171" },
  { id: "automation",   name: "自動化・プログラマビリティ", weight: 10, icon: "🤖", color: "#f472b6" },
];

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
];
