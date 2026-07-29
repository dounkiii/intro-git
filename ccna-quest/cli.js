/* =====================================================================
 * CCNA Quest - コマンド道場 (Cisco IOS CLIシミュレータ)
 * モード遷移(user/priv/config/if/line/router/vlan/dhcp/acl)を再現し、
 * シナリオごとの必須コマンドをチェックリスト方式で採点する。
 * 略記(conf t, int g0/0, no shut ...)や do 前置に対応。
 * ===================================================================== */

/* ---- 略記展開 & 正規化 ---- */
function normCmd(raw) {
  let s = raw.trim().toLowerCase().replace(/\s+/g, " ");
  if (!s) return "";
  // インタフェース名の正規化
  s = s.replace(/\bgi?(gabitethernet)?\s*([0-9]\/[0-9](\/[0-9]+)?)/g, "gigabitethernet$2")
       .replace(/\bfa?(stethernet)?\s*([0-9]\/[0-9]+)/g, "fastethernet$2");
  // よく使う略記
  const map = [
    [/^conf(igure)?( t(erminal)?)?$/, "configure terminal"],
    [/^en(able)?$/, "enable"],
    [/^dis(able)?$/, "disable"],
    [/^no shut(down)?$/, "no shutdown"],
    [/^shut(down)?$/, "shutdown"],
    [/^wr(ite)?( mem(ory)?)?$/, "write"],
    [/^copy run(ning-config)? start(up-config)?$/, "write"],
    [/^int(erface)? /, "interface "],
    [/^sh(ow)? /, "show "],
    [/^ex(it)?$/, "exit"],
  ];
  for (const [re, val] of map) if (re.test(s)) s = s.replace(re, val);
  return s;
}

const CLI_SCENARIOS = [
  {
    id: "setup", title: "初期設定 & SSH", diff: 1,
    brief: "ルータ R1 の初期設定を行い、安全なリモート管理(SSH)を有効化せよ。",
    tasks: [
      "特権EXECモードに入る",
      "グローバルコンフィグに入る",
      "ホスト名を R1 にする",
      "enable secret を Cisco123 に設定",
      "ドメイン名を example.com に設定",
      "ユーザ admin をsecret AdminPass で作成",
      "RSA鍵を生成 (modulus 1024)",
      "VTYライン 0-4 に入り、login local と transport input ssh を設定",
      "設定を保存する",
    ],
    device: "Router",
    goals: [
      { m: "priv",   c: "enable" },
      { m: "config", c: "configure terminal", from: "priv" },
      { m: "config", c: "hostname r1" },
      { m: "config", c: /^enable secret \S+$/ },
      { m: "config", c: /^ip domain[- ]name \S+$/ },
      { m: "config", c: /^username \w+ secret \S+$/ },
      { m: "config", c: /^crypto key generate rsa( modulus \d+)?$/ },
      { m: "line",   c: "line vty 0 4", from: "config" },
      { m: "line",   c: "login local" },
      { m: "line",   c: "transport input ssh" },
      { m: "priv",   c: "write" },
    ],
  },
  {
    id: "ipaddr", title: "インタフェースIP設定", diff: 1,
    brief: "R1 の g0/0 に 192.168.1.1/24 を設定し、リンクアップさせよ。",
    device: "R1",
    tasks: [
      "特権EXEC → グローバルコンフィグへ",
      "interface g0/0 に入る",
      "ip address 192.168.1.1 255.255.255.0",
      "no shutdown でリンクアップ",
      "show ip interface brief で確認",
    ],
    goals: [
      { m: "config", c: "configure terminal", from: "priv" },
      { m: "if",     c: "interface gigabitethernet0/0", from: "config" },
      { m: "if",     c: "ip address 192.168.1.1 255.255.255.0" },
      { m: "if",     c: "no shutdown" },
    ],
  },
  {
    id: "vlan", title: "VLAN & トランク", diff: 2,
    brief: "SW1 で VLAN 10(SALES)を作成し、f0/1 をアクセスポート、g0/1 をトランクにせよ。",
    device: "SW1",
    tasks: [
      "VLAN 10 を作成し name SALES",
      "f0/1 を switchport mode access + access vlan 10",
      "g0/1 を switchport mode trunk",
      "show vlan brief で確認",
    ],
    goals: [
      { m: "vlan",   c: "vlan 10", from: "config" },
      { m: "vlan",   c: "name sales" },
      { m: "if",     c: "interface fastethernet0/1", from: "config" },
      { m: "if",     c: "switchport mode access" },
      { m: "if",     c: "switchport access vlan 10" },
      { m: "if",     c: "interface gigabitethernet0/1" },
      { m: "if",     c: "switchport mode trunk" },
    ],
  },
  {
    id: "route", title: "スタティック & デフォルトルート", diff: 2,
    brief: "R1 に 192.168.2.0/24 → 10.0.0.2 の経路と、デフォルトルートを設定せよ。",
    device: "R1",
    tasks: [
      "ip route 192.168.2.0 255.255.255.0 10.0.0.2",
      "デフォルトルート ip route 0.0.0.0 0.0.0.0 10.0.0.2",
      "show ip route で確認",
    ],
    goals: [
      { m: "config", c: "configure terminal", from: "priv" },
      { m: "config", c: "ip route 192.168.2.0 255.255.255.0 10.0.0.2" },
      { m: "config", c: "ip route 0.0.0.0 0.0.0.0 10.0.0.2" },
    ],
  },
  {
    id: "ospf", title: "OSPFv2 シングルエリア", diff: 3,
    brief: "R1 で OSPF プロセス1 を起動し、router-id 1.1.1.1、192.168.1.0/24 と 10.0.0.0/30 を area 0 に広告せよ。",
    device: "R1",
    tasks: [
      "router ospf 1",
      "router-id 1.1.1.1",
      "network 192.168.1.0 0.0.0.255 area 0 (ワイルドカードマスクに注意)",
      "network 10.0.0.0 0.0.0.3 area 0",
    ],
    goals: [
      { m: "router", c: "router ospf 1", from: "config" },
      { m: "router", c: "router-id 1.1.1.1" },
      { m: "router", c: "network 192.168.1.0 0.0.0.255 area 0" },
      { m: "router", c: "network 10.0.0.0 0.0.0.3 area 0" },
    ],
  },
  {
    id: "portsec", title: "ポートセキュリティ", diff: 3,
    brief: "SW1 の f0/1 をアクセスポートにし、最大2 MAC・sticky学習・違反時 shutdown を設定せよ。",
    device: "SW1",
    tasks: [
      "f0/1 を switchport mode access",
      "switchport port-security を有効化",
      "maximum 2 / mac-address sticky",
      "violation shutdown",
    ],
    goals: [
      { m: "if", c: "interface fastethernet0/1", from: "config" },
      { m: "if", c: "switchport mode access" },
      { m: "if", c: "switchport port-security" },
      { m: "if", c: "switchport port-security maximum 2" },
      { m: "if", c: "switchport port-security mac-address sticky" },
      { m: "if", c: "switchport port-security violation shutdown" },
    ],
  },
];

const CLI = {
  sc: null, mode: "user", host: "Router", done: [], hintIdx: 0,

  start(idx) {
    this.sc = CLI_SCENARIOS[idx];
    this.mode = "user";
    this.host = this.sc.device;
    this.done = this.sc.goals.map(() => false);
    this.hintIdx = 0;
    document.getElementById("cli-title").textContent = this.sc.title;
    document.getElementById("cli-brief").textContent = this.sc.brief;
    document.getElementById("cli-out").innerHTML = "";
    this.print(`--- ${this.sc.title} ---`, "sys");
    this.print("課題: " + this.sc.brief, "sys");
    this.print("ヒントが欲しいときは『次のコマンド例』ボタン。'?' でモード確認。", "sys");
    this.renderTasks();
    go("cli");
    setTimeout(() => document.getElementById("cli-input").focus(), 50);
    this.updatePrompt();
  },

  renderList() {
    const wrap = document.getElementById("cli-list");
    wrap.innerHTML = "";
    CLI_SCENARIOS.forEach((s, i) => {
      const done = (S.cliCleared || []).includes(s.id);
      const el = document.createElement("div");
      el.className = "card mode cli-card";
      el.innerHTML = `<div class="diff-badge d${s.diff}">${["", "初級", "中級", "上級"][s.diff]}</div>
        <h3>${s.title} ${done ? "✅" : ""}</h3><p>${s.brief}</p>`;
      el.onclick = () => this.start(i);
      wrap.appendChild(el);
    });
  },

  promptStr() {
    const suffix = {
      user: ">", priv: "#", config: "(config)#", if: "(config-if)#",
      line: "(config-line)#", router: "(config-router)#", vlan: "(config-vlan)#",
      dhcp: "(dhcp-config)#", acl: "(config-nacl)#",
    }[this.mode];
    return this.host + suffix;
  },
  updatePrompt() { document.getElementById("cli-prompt").textContent = this.promptStr(); },

  print(txt, cls = "") {
    const out = document.getElementById("cli-out");
    const line = document.createElement("div");
    line.className = "cli-line " + cls;
    line.textContent = txt;
    out.appendChild(line);
    out.scrollTop = out.scrollHeight;
  },

  submit() {
    const inp = document.getElementById("cli-input");
    const raw = inp.value;
    inp.value = "";
    if (!raw.trim()) return;
    this.print(this.promptStr() + " " + raw, "echo");
    this.exec(raw);
  },

  exec(raw) {
    let s = normCmd(raw);

    // do 前置: 特権EXECコマンドを設定モードから実行
    if (s.startsWith("do ")) s = s.slice(3);

    if (s === "?") { this.print("現在のモード: " + this.modeName() + " / プロンプト: " + this.promptStr(), "sys"); return; }

    // ---- モード遷移 ----
    if (s === "enable") {
      if (this.mode === "user") { this.mode = "priv"; this.updatePrompt(); this.check("priv", "enable"); }
      else this.err("enable はユーザEXEC(>)から実行します");
      return;
    }
    if (s === "disable") { this.mode = "user"; this.updatePrompt(); return; }
    if (s === "configure terminal") {
      if (this.mode === "priv") { this.mode = "config"; this.updatePrompt(); this.check("config", "configure terminal", "priv"); }
      else this.err("configure terminal は特権EXEC(#)から実行します");
      return;
    }
    if (s === "end") { if (this.mode !== "user") this.mode = this.mode === "priv" ? "priv" : "priv"; this.mode = (this.mode === "user") ? "user" : "priv"; this.updatePrompt(); return; }
    if (s === "exit") { this.exitMode(); return; }

    // 設定サブモードへの遷移(グローバルconfigから)
    if (this.mode === "config" || /^(if|line|router|vlan|dhcp|acl)$/.test(this.mode)) {
      let mm;
      if (/^interface \S+$/.test(s)) mm = "if";
      else if (/^line (console|vty|aux)\b/.test(s)) mm = "line";
      else if (/^router (ospf|eigrp|rip)\b/.test(s)) mm = "router";
      else if (/^vlan \d+$/.test(s)) mm = "vlan";
      else if (/^ip dhcp pool \S+$/.test(s)) mm = "dhcp";
      else if (/^ip access-list (standard|extended) \S+$/.test(s)) mm = "acl";
      if (mm) {
        if (this.mode === "config" || this.mode === mm || ["if", "line", "router", "vlan", "dhcp", "acl"].includes(this.mode)) {
          this.mode = mm; this.updatePrompt();
          this.check(mm, s, "config");
          return;
        }
      }
    }

    // hostname はプロンプトを変える
    const hn = s.match(/^hostname (\S+)$/);
    if (hn && this.mode === "config") { this.host = raw.trim().split(/\s+/)[1]; this.updatePrompt(); this.check("config", s); return; }

    // show コマンド(簡易出力)
    if (s.startsWith("show ")) {
      if (this.mode === "user" || this.mode === "priv") { this.showCmd(s); this.check(this.mode, s); }
      else this.err("show は 'do " + s + "' で設定モードからも実行できます");
      return;
    }

    // 一般コマンド → ゴール照合
    if (!this.check(this.mode, s)) {
      // モード不一致の可能性を判定
      const inWrongMode = this.sc.goals.some(g => this.matches(g, s) && !this.modeOk(g.m));
      if (inWrongMode) this.err("そのコマンドはこのモードでは実行できません。正しい設定モードに入りましょう。");
      else this.print("% 認識できないコマンド、またはこのシナリオでは不要です。", "err");
    }
  },

  matches(goal, s) {
    return goal.c instanceof RegExp ? goal.c.test(s) : goal.c === s;
  },
  modeOk(m) { return this.mode === m; },

  check(mode, s, requireFrom) {
    let hit = false;
    this.sc.goals.forEach((g, i) => {
      if (this.done[i]) return;
      if (this.matches(g, s) && g.m === mode) {
        this.done[i] = true; hit = true;
        this.print("✔ OK: " + s, "ok");
      }
    });
    if (hit) { this.renderTasks(); this.maybeFinish(); }
    return hit;
  },

  maybeFinish() {
    if (this.done.every(Boolean)) {
      this.print("🎉 すべての設定が完了しました！", "ok");
      if (!S.cliCleared) S.cliCleared = [];
      const first = !S.cliCleared.includes(this.sc.id);
      if (first) { S.cliCleared.push(this.sc.id); addXP(30 + this.sc.diff * 10); }
      if (S.cliCleared.length >= CLI_SCENARIOS.length) unlock("cli_master");
      unlock("cli_first");
      save();
      setTimeout(() => {
        document.getElementById("res-emoji").textContent = "⌨️";
        document.getElementById("res-score").textContent = "シナリオ完了！";
        document.getElementById("res-xp").textContent = first ? `+${30 + this.sc.diff * 10} XP` : "(クリア済み)";
        document.getElementById("res-msg").textContent = "実機と同じ手順を再現できました。次のシナリオにも挑戦しよう。";
        document.getElementById("res-again").textContent = "コマンド道場へ戻る";
        document.getElementById("res-again").onclick = () => { CLI.renderList(); go("cli-menu"); };
        renderStats(); renderHUD();
        go("result");
      }, 700);
    }
  },

  exitMode() {
    const up = { if: "config", line: "config", router: "config", vlan: "config", dhcp: "config", acl: "config", config: "priv", priv: "user", user: "user" };
    this.mode = up[this.mode] || "user";
    this.updatePrompt();
  },

  err(msg) { this.print("% " + msg, "err"); },
  modeName() {
    return { user: "ユーザEXEC", priv: "特権EXEC", config: "グローバル設定", if: "インタフェース設定",
      line: "ライン設定", router: "ルーティングプロセス設定", vlan: "VLAN設定", dhcp: "DHCPプール設定", acl: "ACL設定" }[this.mode];
  },

  showCmd(s) {
    if (s.includes("ip interface brief") || s.includes("ip int brief")) {
      this.print("Interface              IP-Address      OK? Method Status    Protocol", "mono");
      this.print("GigabitEthernet0/0     192.168.1.1     YES manual up        up", "mono");
      this.print("GigabitEthernet0/1     unassigned      YES unset  admin down down", "mono");
    } else if (s.includes("vlan brief")) {
      this.print("VLAN Name       Status    Ports", "mono");
      this.print("10   SALES      active    Fa0/1", "mono");
    } else if (s.includes("ip route")) {
      this.print("S*   0.0.0.0/0 [1/0] via 10.0.0.2", "mono");
      this.print("S    192.168.2.0/24 [1/0] via 10.0.0.2", "mono");
    } else if (s.includes("running-config")) {
      this.print("(現在の設定が表示されます)", "mono");
    } else {
      this.print("(出力は省略されています)", "mono");
    }
  },

  hint() {
    const nextIdx = this.done.findIndex(d => !d);
    if (nextIdx < 0) { this.print("すべて完了しています！", "sys"); return; }
    const g = this.sc.goals[nextIdx];
    const example = g.c instanceof RegExp
      ? g.c.source.replace(/\\S\+/g, "<値>").replace(/[\\^$()?]/g, "").replace(/\|/g, " または ")
      : g.c;
    this.print(`💡 次の例 [${this.modeLabel(g.m)}]: ${example}`, "hint");
  },
  modeLabel(m) { return this.modeName.call({ mode: m }) || m; },

  renderTasks() {
    const wrap = document.getElementById("cli-tasks");
    wrap.innerHTML = this.sc.tasks.map((t, i) => {
      // タスクとゴールは1:1ではないため、達成数で概算表示
      return `<li>${t}</li>`;
    }).join("");
    const doneN = this.done.filter(Boolean).length;
    document.getElementById("cli-progress").textContent = `${doneN} / ${this.done.length} コマンド完了`;
    document.getElementById("cli-progbar").style.width = (doneN / this.done.length * 100) + "%";
  },
};
