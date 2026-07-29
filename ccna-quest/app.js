/* =====================================================================
 * CCNA Quest - アプリロジック
 * 状態管理 / XP・レベル / 各ゲームモード / 実績 / 永続化(localStorage)
 * ===================================================================== */

"use strict";

/* ---------------------- 状態管理 ---------------------- */
const SAVE_KEY = "ccna_quest_save_v1";
const DEFAULT_STATE = {
  xp: 0,
  streak: 0,
  lastPlay: null,          // "YYYY-MM-DD"
  quizzesCleared: 0,
  bestCombo: 0,
  subnetCorrect: 0,
  flashSeen: [],           // 確認済みフラッシュカードindex
  domainsCleared: [],      // クリアした領域id
  achievements: [],        // 解除済みバッジid
  adventure: { chapter: 0, stage: 0, hpBonus: 0, _replay: null }, // アドベンチャー進行
  cliCleared: [],          // クリアしたCLIシナリオid
  rushBest: 0,             // サブネット・ラッシュ自己ベスト
  examTaken: 0,            // 模擬試験受験回数
  examBest: 0,             // 模擬試験の最高スコア
};

let S = load();

function load() {
  try {
    const raw = localStorage.getItem(SAVE_KEY);
    if (raw) {
      const s = Object.assign({}, DEFAULT_STATE, JSON.parse(raw));
      s.adventure = Object.assign({ chapter: 0, stage: 0, hpBonus: 0, _replay: null }, s.adventure || {});
      return s;
    }
  } catch (e) { /* ignore */ }
  const d = JSON.parse(JSON.stringify(DEFAULT_STATE));
  return d;
}
function save() {
  try { localStorage.setItem(SAVE_KEY, JSON.stringify(S)); } catch (e) {}
}

/* ---------------------- XP / レベル ---------------------- */
// レベルnに到達するのに必要な累計XP: 50 * n * (n-1)
function levelFromXP(xp) {
  let lvl = 1;
  while (xp >= 50 * (lvl) * (lvl + 1)) lvl++;
  return lvl;
}
function xpForLevel(lvl) { return 50 * (lvl - 1) * lvl; }

function addXP(amount) {
  const before = levelFromXP(S.xp);
  S.xp += amount;
  const after = levelFromXP(S.xp);
  save();
  renderHUD();
  if (after > before) {
    toast(`🎉 レベルアップ！ Lv.${after} になりました`);
    if (after >= 5)  unlock("level5");
    if (after >= 10) unlock("level10");
  }
}

/* ---------------------- 連続学習(ストリーク) ---------------------- */
function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function daysBetween(a, b) {
  return Math.round((new Date(b) - new Date(a)) / 86400000);
}
function touchStreak() {
  const today = todayStr();
  if (S.lastPlay === today) return;
  if (S.lastPlay && daysBetween(S.lastPlay, today) === 1) S.streak += 1;
  else S.streak = 1;
  S.lastPlay = today;
  save();
  if (S.streak >= 3) unlock("streak3");
  renderHUD();
}

/* ---------------------- 実績 ---------------------- */
function unlock(id) {
  if (S.achievements.includes(id)) return;
  const a = ACHIEVEMENTS.find(x => x.id === id);
  if (!a) return;
  S.achievements.push(id);
  save();
  toast(`${a.icon} 実績解除: ${a.name}`);
  renderAchievements();
}

/* ---------------------- 画面遷移 ---------------------- */
const VIEWS = ["home", "quiz-setup", "quiz", "subnet", "flash", "ports", "result",
  "adventure", "battle", "exam-setup", "exam", "exam-result", "rush", "cli-menu", "cli"];
function go(view) {
  VIEWS.forEach(v => document.getElementById("view-" + v).classList.toggle("hidden", v !== view));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ---------------------- トースト / コンボ演出 ---------------------- */
let toastTimer;
function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
}
let comboTimer;
function popCombo(text) {
  const c = document.getElementById("combo");
  c.textContent = text;
  c.classList.add("pop");
  clearTimeout(comboTimer);
  comboTimer = setTimeout(() => c.classList.remove("pop"), 700);
}

/* ---------------------- 汎用 ---------------------- */
function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}
function domainName(id) {
  const d = CCNA_DOMAINS.find(x => x.id === id);
  return d ? d.name : id;
}

/* =====================================================================
 * クイズモード
 * ===================================================================== */
const Quiz = {
  queue: [], idx: 0, score: 0, combo: 0, correctCount: 0, domain: "random", diff: "all",

  start() {
    const domSel = document.getElementById("quiz-domain").value;
    const diffSel = document.getElementById("quiz-diff").value;
    const count = parseInt(document.getElementById("quiz-count").value, 10);
    let pool = QUIZ_BANK.slice();
    if (domSel !== "random") pool = pool.filter(q => q.domain === domSel);
    if (diffSel !== "all") pool = pool.filter(q => q.diff === parseInt(diffSel, 10));
    if (pool.length === 0) { toast("該当する問題がありません"); return; }
    pool = shuffle(pool).slice(0, count);
    this.queue = pool.map(q => {
      const order = shuffle(q.choices.map((c, i) => i));
      const ansArr = (Array.isArray(q.answer) ? q.answer : [q.answer]).map(a => order.indexOf(a));
      return {
        q: q.q, exp: q.exp, domain: q.domain, diff: q.diff, fig: q.fig,
        choices: order.map(i => q.choices[i]),
        answer: ansArr, multi: Array.isArray(q.answer),
      };
    });
    this.idx = 0; this.score = 0; this.combo = 0; this.correctCount = 0; this.domain = domSel;
    touchStreak();
    go("quiz");
    this.render();
  },

  render() {
    const item = this.queue[this.idx];
    this._picked = new Set();
    document.getElementById("q-progress").textContent =
      `${domainName(item.domain)}・${DIFF_LABELS[item.diff]} — 第${this.idx + 1}問 / ${this.queue.length}`;
    document.getElementById("q-combo").textContent = this.combo;
    document.getElementById("q-score").textContent = this.score;
    document.getElementById("q-bar").style.width = (this.idx / this.queue.length * 100) + "%";
    document.getElementById("q-fig").innerHTML = item.fig ? Art.diagram(item.fig) : "";
    document.getElementById("q-text").textContent = item.q;
    document.getElementById("q-multi").classList.toggle("hidden", !item.multi);

    const box = document.getElementById("q-choices");
    box.innerHTML = "";
    const keys = ["A", "B", "C", "D", "E"];
    item.choices.forEach((c, i) => {
      const b = document.createElement("button");
      b.className = "choice";
      b.innerHTML = `<span class="key">${keys[i]}</span><span>${c}</span>`;
      b.onclick = () => item.multi ? this.togglePick(i, b) : this.answer([i]);
      box.appendChild(b);
    });
    document.getElementById("q-exp").className = "exp";
    document.getElementById("q-next-row").classList.add("hidden");
    // 複数選択なら「決定」ボタン、単一選択なら押した瞬間に判定
    document.getElementById("q-confirm-row").classList.toggle("hidden", !item.multi);
    if (item.multi) document.getElementById("q-confirm").disabled = true;
  },

  togglePick(i, btn) {
    if (this._picked.has(i)) { this._picked.delete(i); btn.classList.remove("sel"); }
    else { this._picked.add(i); btn.classList.add("sel"); }
    document.getElementById("q-confirm").disabled = this._picked.size === 0;
  },
  confirmMulti() { this.answer([...this._picked]); },

  answer(picked) {
    const item = this.queue[this.idx];
    const buttons = [...document.querySelectorAll("#q-choices .choice")];
    buttons.forEach(b => b.disabled = true);
    document.getElementById("q-confirm-row").classList.add("hidden");
    const exp = document.getElementById("q-exp");
    const correct = item.answer.slice().sort((a, b) => a - b);
    const pick = picked.slice().sort((a, b) => a - b);
    const ok = pick.length === correct.length && pick.every((v, k) => v === correct[k]);

    // 色付け
    correct.forEach(i => buttons[i].classList.add("correct"));
    pick.forEach(i => { if (!correct.includes(i)) buttons[i].classList.add("wrong"); });

    if (ok) {
      this.combo += 1; this.correctCount += 1;
      const bonus = item.diff * 4; // 難しい問題ほど高得点
      const gained = 10 + Math.min(this.combo - 1, 10) * 2 + bonus;
      this.score += gained;
      if (this.combo >= 2) popCombo(`${this.combo} COMBO! +${gained}XP`);
      if (this.combo > S.bestCombo) S.bestCombo = this.combo;
      if (this.combo >= 10) unlock("combo10");
      exp.className = "exp ok show";
      exp.innerHTML = `<span class="tag">正解！ +${gained}XP</span>${item.exp}`;
    } else {
      this.combo = 0;
      exp.className = "exp ng show";
      exp.innerHTML = `<span class="tag">不正解</span>${item.exp}`;
    }
    document.getElementById("q-combo").textContent = this.combo;
    document.getElementById("q-score").textContent = this.score;
    document.getElementById("q-next").textContent =
      this.idx + 1 < this.queue.length ? "次へ →" : "結果を見る";
    document.getElementById("q-next-row").classList.remove("hidden");
    save();
  },

  next() {
    this.idx += 1;
    if (this.idx < this.queue.length) this.render();
    else this.finish();
  },

  finish() {
    const total = this.queue.length;
    const perfect = this.correctCount === total;
    addXP(this.score);
    S.quizzesCleared += 1;
    if (this.domain !== "random" && !S.domainsCleared.includes(this.domain)) {
      S.domainsCleared.push(this.domain);
    }
    unlock("first_quiz");
    if (perfect) unlock("perfect");
    // 全領域制覇判定
    const realDomains = CCNA_DOMAINS.map(d => d.id);
    if (realDomains.every(d => S.domainsCleared.includes(d))) unlock("all_domains");
    save();

    document.getElementById("res-emoji").textContent = perfect ? "🏆" : this.correctCount >= total * 0.6 ? "🎉" : "💪";
    document.getElementById("res-score").textContent = `${this.correctCount} / ${total} 正解`;
    document.getElementById("res-xp").textContent = `+${this.score} XP 獲得`;
    document.getElementById("res-msg").textContent = perfect
      ? "パーフェクト！この領域はバッチリです。"
      : this.correctCount >= total * 0.6
        ? "good! 間違えた問題の解説を復習しよう。"
        : "まずは解説を読んで用語に慣れよう。繰り返せば必ず定着します。";
    document.getElementById("res-again").onclick = () => go("quiz-setup");
    renderStats(); renderHUD();
    go("result");
  },

  quit() { if (confirm("クイズを中断してホームに戻りますか？")) go("home"); },
};

/* =====================================================================
 * サブネット道場 (無限に問題を自動生成)
 * ===================================================================== */
const Subnet = {
  cur: null,

  newQ() {
    // /8 〜 /30 の範囲でランダムなCIDRを生成
    const prefix = 8 + Math.floor(Math.random() * 23); // 8..30
    const ip = [
      10 + Math.floor(Math.random() * 200),
      Math.floor(Math.random() * 256),
      Math.floor(Math.random() * 256),
      Math.floor(Math.random() * 256),
    ];
    this.cur = this.compute(ip, prefix);
    document.getElementById("sub-prompt").textContent =
      "次のIP/CIDRについて、ネットワークアドレス・ブロードキャスト・利用可能ホスト数を求めよ。";
    document.getElementById("sub-q").textContent = `${ip.join(".")}/${prefix}`;

    const fields = [
      { id: "net", label: "ネットワークアドレス", ph: "例: 192.168.1.0" },
      { id: "mask", label: "サブネットマスク(10進)", ph: "例: 255.255.255.0" },
      { id: "bc", label: "ブロードキャストアドレス", ph: "例: 192.168.1.255" },
      { id: "hosts", label: "利用可能ホスト数", ph: "例: 254" },
    ];
    document.getElementById("sub-fields").innerHTML = fields.map(f =>
      `<div><label>${f.label}</label><input type="text" id="sub-${f.id}" placeholder="${f.ph}" autocomplete="off"></div>`
    ).join("");
    document.getElementById("sub-exp").className = "exp";
    document.getElementById("sub-check").disabled = false;
    document.getElementById("sub-fields").querySelector("input").focus();
  },

  compute(ip, prefix) {
    const ipInt = ip.reduce((a, o) => (a << 8 >>> 0) + o, 0) >>> 0;
    const mask = prefix === 0 ? 0 : (0xFFFFFFFF << (32 - prefix)) >>> 0;
    const net = (ipInt & mask) >>> 0;
    const bc = (net | (~mask >>> 0)) >>> 0;
    const hostBits = 32 - prefix;
    const hosts = hostBits <= 1 ? (hostBits === 1 ? 2 : 1) : (Math.pow(2, hostBits) - 2);
    return {
      prefix,
      net: this.toStr(net),
      mask: this.toStr(mask),
      bc: this.toStr(bc),
      hosts: prefix >= 31 ? (prefix === 31 ? 2 : 1) : hosts, // /31,/32は特殊
    };
  },
  toStr(int) {
    return [(int >>> 24) & 255, (int >>> 16) & 255, (int >>> 8) & 255, int & 255].join(".");
  },
  norm(s) { return (s || "").trim().replace(/\s/g, ""); },

  check() {
    const c = this.cur;
    const g = id => this.norm(document.getElementById("sub-" + id).value);
    const checks = [
      { id: "net", ok: g("net") === c.net, want: c.net, label: "ネットワークアドレス" },
      { id: "mask", ok: g("mask") === c.mask, want: c.mask, label: "サブネットマスク" },
      { id: "bc", ok: g("bc") === c.bc, want: c.bc, label: "ブロードキャスト" },
      { id: "hosts", ok: g("hosts") === String(c.hosts), want: String(c.hosts), label: "ホスト数" },
    ];
    checks.forEach(ch => {
      const el = document.getElementById("sub-" + ch.id);
      el.style.borderColor = ch.ok ? "var(--good)" : "var(--bad)";
    });
    const allOk = checks.every(ch => ch.ok);
    const exp = document.getElementById("sub-exp");
    exp.className = "exp show " + (allOk ? "ok" : "ng");

    if (allOk) {
      S.subnetCorrect += 1;
      this._streak = (this._streak || 0) + 1;
      const gained = 8 + Math.min(this._streak, 6);
      addXP(gained);
      if (S.subnetCorrect >= 25) unlock("subnet25");
      exp.innerHTML = `<span class="tag" style="color:var(--good)">全問正解！ +${gained}XP</span>` + this.explain(c);
      document.getElementById("sub-check").disabled = true;
    } else {
      this._streak = 0;
      exp.innerHTML = `<span class="tag" style="color:var(--bad)">おしい！正解はこちら</span>` +
        checks.filter(ch => !ch.ok).map(ch => `<div>・${ch.label}: <b>${ch.want}</b></div>`).join("") +
        `<hr style="border-color:var(--line)">` + this.explain(c);
    }
    document.getElementById("sub-streak").textContent = this._streak || 0;
    document.getElementById("sub-total").textContent = S.subnetCorrect;
    save();
  },

  explain(c) {
    const hostBits = 32 - c.prefix;
    return `<div class="muted" style="margin-top:8px">
      /${c.prefix} → マスク <b>${c.mask}</b>。ホストビットは <b>${hostBits}</b> ビットなので、
      アドレス数は 2<sup>${hostBits}</sup>=${Math.pow(2, hostBits)}、
      うち先頭(ネットワーク)と末尾(ブロードキャスト)を除いた <b>${c.hosts}</b> がホストに使えます。</div>`;
  },
};

/* =====================================================================
 * フラッシュカード
 * ===================================================================== */
const Flash = {
  order: [], idx: 0,
  start() {
    this.order = shuffle(FLASHCARDS.map((_, i) => i));
    this.idx = 0;
    touchStreak();
    go("flash");
    this.render();
  },
  render() {
    const card = FLASHCARDS[this.order[this.idx]];
    document.getElementById("flip").classList.remove("flipped");
    document.getElementById("flash-domain").textContent = domainName(card.domain);
    document.getElementById("flash-front").textContent = card.front;
    document.getElementById("flash-back").textContent = card.back;
    document.getElementById("flash-progress").textContent = `${this.idx + 1} / ${FLASHCARDS.length}`;
    // 確認済み記録
    const realIdx = this.order[this.idx];
    if (!S.flashSeen.includes(realIdx)) {
      S.flashSeen.push(realIdx);
      if (S.flashSeen.length === 1) addXP(5);
      if (S.flashSeen.length >= FLASHCARDS.length) unlock("flash_all");
      save();
    }
  },
  flip() { document.getElementById("flip").classList.toggle("flipped"); },
  next() { this.idx = (this.idx + 1) % FLASHCARDS.length; this.render(); },
  prev() { this.idx = (this.idx - 1 + FLASHCARDS.length) % FLASHCARDS.length; this.render(); },
};

/* =====================================================================
 * ポート & プロトコル マッチングゲーム
 * ===================================================================== */
const Ports = {
  set: [], selLeft: null, selRight: null, remaining: 0,

  start() {
    this.set = shuffle(PORTS).slice(0, 8);
    this.remaining = this.set.length;
    this.selLeft = this.selRight = null;
    touchStreak();
    go("ports");
    this.render();
  },
  render() {
    const left = document.getElementById("ports-left-col");
    const right = document.getElementById("ports-right-col");
    left.innerHTML = ""; right.innerHTML = "";
    document.getElementById("ports-left").textContent = this.remaining;

    this.set.forEach((p, i) => {
      const l = document.createElement("div");
      l.className = "tile"; l.textContent = p.proto; l.dataset.i = i;
      l.onclick = () => this.pick("left", i, l);
      left.appendChild(l);
    });
    shuffle(this.set.map((_, i) => i)).forEach(i => {
      const p = this.set[i];
      const r = document.createElement("div");
      r.className = "tile port"; r.dataset.i = i;
      r.innerHTML = `${p.port}<span class="layer">${p.layer}</span>`;
      r.onclick = () => this.pick("right", i, r);
      right.appendChild(r);
    });
  },
  pick(side, i, el) {
    const key = side === "left" ? "selLeft" : "selRight";
    // 同じ列の選択をクリア
    document.querySelectorAll(`#ports-${side}-col .tile`).forEach(t => t.classList.remove("sel"));
    el.classList.add("sel");
    this[key] = { i, el };
    if (this.selLeft && this.selRight) this.evaluate();
  },
  evaluate() {
    const L = this.selLeft, R = this.selRight;
    if (L.i === R.i) {
      L.el.classList.add("done"); R.el.classList.add("done");
      L.el.classList.remove("sel"); R.el.classList.remove("sel");
      addXP(6);
      this.remaining -= 1;
      document.getElementById("ports-left").textContent = this.remaining;
      if (this.remaining === 0) {
        unlock("ports_perfect");
        setTimeout(() => {
          document.getElementById("res-emoji").textContent = "🚪";
          document.getElementById("res-score").textContent = "コンプリート！";
          document.getElementById("res-xp").textContent = `+${this.set.length * 6} XP`;
          document.getElementById("res-msg").textContent = "全ペアを繋げました。ポート番号はCCNA頻出です！";
          document.getElementById("res-again").onclick = () => Ports.start();
          go("result");
        }, 400);
      }
    } else {
      [L.el, R.el].forEach(e => { e.classList.add("miss"); setTimeout(() => e.classList.remove("miss", "sel"), 350); });
    }
    this.selLeft = this.selRight = null;
  },
};

/* =====================================================================
 * ホーム画面の描画
 * ===================================================================== */
const MODES = [
  { emoji: "🗺️", title: "アドベンチャー", tag: "RPGバトル", feat: true,
    desc: "パケットンを操作してモンスターと問題バトル。素早い正解でクリティカル！章を進めて全領域を制覇。",
    act: () => { Adventure.renderMap(); go("adventure"); } },
  { emoji: "📝", title: "模擬試験", tag: "本番形式",
    desc: "本番同様の制限時間・リニア形式。1000点満点で採点し分野別に弱点を可視化。",
    act: () => Exam.setup() },
  { emoji: "⚡", title: "サブネット・ラッシュ", tag: "タイムアタック",
    desc: "制限時間との戦い。高速でサブネット問題を解いてコンボと速度を上げろ！",
    act: () => Rush.start() },
  { emoji: "⌨️", title: "コマンド道場", tag: "CLIシミュレータ",
    desc: "本物そっくりのCisco IOS端末で設定を練習。モード遷移も再現。",
    act: () => { CLI.renderList(); go("cli-menu"); } },
  { emoji: "🎯", title: "クイズ", tag: "難易度選択",
    desc: "初級〜本番レベルを選んで4択演習。コンボでXPアップ。",
    act: () => go("quiz-setup") },
  { emoji: "🃏", title: "フラッシュカード", tag: "暗記",
    desc: "重要用語をめくって暗記。", act: () => Flash.start() },
  { emoji: "🚪", title: "ポート&プロトコル", tag: "ミニゲーム",
    desc: "番号とプロトコルを繋ぐマッチゲーム。", act: () => Ports.start() },
];

function renderModes() {
  const grid = document.getElementById("mode-grid");
  grid.innerHTML = "";
  MODES.forEach(m => {
    const d = document.createElement("div");
    d.className = "card mode" + (m.feat ? " featured" : "");
    d.innerHTML = `<div class="mode-top"><span class="emoji">${m.emoji}</span><span class="mode-tag">${m.tag}</span></div>
      <h3>${m.title}</h3><p>${m.desc}</p>`;
    d.onclick = m.act;
    grid.appendChild(d);
  });

  // クイズ設定の領域・難易度セレクト
  const sel = document.getElementById("quiz-domain");
  sel.innerHTML = `<option value="random">🎲 ランダム(全領域)</option>` +
    CCNA_DOMAINS.map(d => `<option value="${d.id}">${d.icon} ${d.name} (${d.weight}%)</option>`).join("");
  const dsel = document.getElementById("quiz-diff");
  dsel.innerHTML = `<option value="all">全難易度</option>
    <option value="1">初級</option><option value="2">中級</option><option value="3">本番レベル</option>`;

  // マスコット挨拶
  const mascot = document.getElementById("mascot");
  if (mascot) mascot.innerHTML = Art.hero("happy");
}

function renderStats() {
  const row = document.getElementById("stat-row");
  const lvl = levelFromXP(S.xp);
  row.innerHTML = [
    { b: lvl, s: "レベル" },
    { b: S.xp, s: "累計XP" },
    { b: S.streak + "日", s: "連続学習" },
    { b: S.bestCombo, s: "最高コンボ" },
    { b: S.quizzesCleared, s: "クイズ回数" },
    { b: S.subnetCorrect, s: "サブネット正解" },
  ].map(x => `<div class="stat"><b>${x.b}</b><small>${x.s}</small></div>`).join("");
}

function renderAchievements() {
  const grid = document.getElementById("ach-grid");
  grid.innerHTML = "";
  ACHIEVEMENTS.forEach(a => {
    const unlocked = S.achievements.includes(a.id);
    const d = document.createElement("div");
    d.className = "card ach" + (unlocked ? "" : " locked");
    d.innerHTML = `<span class="ico">${a.icon}</span><div><b>${a.name}</b><small>${a.desc}</small></div>`;
    grid.appendChild(d);
  });
}

function renderHUD() {
  const lvl = levelFromXP(S.xp);
  const cur = xpForLevel(lvl), nextL = xpForLevel(lvl + 1);
  const pct = Math.max(0, Math.min(100, (S.xp - cur) / (nextL - cur) * 100));
  document.getElementById("hud-level").textContent = lvl;
  document.getElementById("hud-xp").textContent = S.xp;
  document.getElementById("hud-streak").textContent = S.streak;
  document.getElementById("hud-xpbar").style.width = pct + "%";
}

/* ---------------------- 初期化 ---------------------- */
function init() {
  renderModes();
  renderStats();
  renderAchievements();
  renderHUD();
  go("home");
}
document.addEventListener("DOMContentLoaded", init);
