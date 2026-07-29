/* =====================================================================
 * CCNA Quest - サブネット・ラッシュ (時間制アーケード)
 * テトリス/ぷよ風の緊迫感。制限時間内に高速でサブネット問題を解く。
 * 正解=時間+加算&コンボ / 不正解=時間減。連続正解で難度・速度アップ。
 * ===================================================================== */

const Rush = {
  time: 0, max: 30, score: 0, combo: 0, correct: 0, level: 1, timer: null, running: false, drain: 1,

  start() {
    this.time = this.max = 30;
    this.score = 0; this.combo = 0; this.correct = 0; this.level = 1; this.drain = 1;
    this.running = true;
    touchStreak();
    document.getElementById("rush-over").classList.add("hidden");
    document.getElementById("rush-play").classList.remove("hidden");
    go("rush");
    this.loop();
    this.newQ();
  },

  loop() {
    clearInterval(this.timer);
    let last = Date.now();
    this.timer = setInterval(() => {
      if (!this.running) return;
      const now = Date.now();
      this.time -= (now - last) / 1000 * this.drain;
      last = now;
      if (this.time <= 0) { this.time = 0; this.gameOver(); }
      this.renderTime();
    }, 60);
  },

  renderTime() {
    const pct = Math.max(0, this.time / this.max * 100);
    const bar = document.getElementById("rush-timebar");
    bar.style.width = pct + "%";
    bar.className = "bar-fill" + (pct < 25 ? " low" : pct < 50 ? " mid" : "");
    document.getElementById("rush-clock").textContent = this.time.toFixed(1);
  },

  newQ() {
    if (!this.running) return;
    // レベルに応じて難しいプレフィックスを増やす
    const prefixes = this.level < 3 ? [24, 25, 26] : this.level < 5 ? [24, 25, 26, 27, 28] : [17, 19, 22, 26, 27, 28, 29, 30];
    const prefix = prefixes[Math.floor(Math.random() * prefixes.length)];
    const ip = [10 + Math.floor(Math.random() * 200), rnd(256), rnd(256), 1 + rnd(254)];
    const c = Subnet.compute(ip, prefix);
    const types = [
      { ask: "ネットワークアドレスは？", correct: c.net, gen: () => this.ipDistractors(c.net) },
      { ask: "ブロードキャストアドレスは？", correct: c.bc, gen: () => this.ipDistractors(c.bc) },
      { ask: "利用可能ホスト数は？", correct: String(c.hosts), gen: () => this.hostDistractors(c.hosts, prefix) },
    ];
    const t = types[rnd(types.length)];
    const choices = shuffle([t.correct, ...t.gen()].slice(0, 4));
    // 重複除去の保険
    const uniq = [...new Set(choices)];
    while (uniq.length < 4) uniq.push(uniq[0] + " ");
    this.cur = { correct: t.correct };

    document.getElementById("rush-ip").textContent = `${ip.join(".")}/${prefix}`;
    document.getElementById("rush-ask").textContent = t.ask;
    document.getElementById("rush-level").textContent = this.level;
    document.getElementById("rush-score").textContent = this.score;
    document.getElementById("rush-combo").textContent = this.combo;
    const box = document.getElementById("rush-choices");
    box.innerHTML = "";
    shuffle(uniq).forEach(ch => {
      const b = document.createElement("button");
      b.className = "choice rush-choice";
      b.textContent = ch.trim();
      b.onclick = () => this.answer(ch.trim(), b);
      box.appendChild(b);
    });
  },

  answer(pick, btn) {
    if (!this.running) return;
    if (pick === this.cur.correct) {
      this.combo += 1; this.correct += 1;
      const bonus = 1 + Math.floor(this.combo / 5);
      this.score += 10 * bonus;
      this.time = Math.min(this.max, this.time + 2);
      btn.classList.add("correct");
      if (this.correct % 5 === 0) { this.level += 1; this.drain += 0.25; flash("LEVEL UP! 速度アップ ⚡"); }
      if (this.correct >= 30) unlock("rush30");
      setTimeout(() => this.newQ(), 120);
    } else {
      this.combo = 0;
      this.time = Math.max(0, this.time - 4);
      btn.classList.add("wrong");
      // 正解を一瞬ハイライト
      [...document.querySelectorAll("#rush-choices .rush-choice")].forEach(b => {
        if (b.textContent === this.cur.correct) b.classList.add("correct");
      });
      setTimeout(() => { if (this.time > 0) this.newQ(); }, 500);
    }
    document.getElementById("rush-score").textContent = this.score;
    document.getElementById("rush-combo").textContent = this.combo;
  },

  ipDistractors(ip) {
    const p = ip.split(".").map(Number);
    const out = [];
    const deltas = [[0, 0, 0, 1], [0, 0, 0, -1], [0, 0, 1, 0], [0, 0, -1, 0]];
    for (const d of deltas) {
      const q = p.map((o, i) => o + d[i]);
      if (q.every(o => o >= 0 && o <= 255)) out.push(q.join("."));
      if (out.length >= 3) break;
    }
    return out;
  },
  hostDistractors(h, prefix) {
    const set = new Set();
    set.add(String(h + 2));               // 2^n (引き忘れ)
    set.add(String(Math.max(0, h / 2 | 0))); // 隣の桁
    set.add(String(h * 2 + 2));           // 一つ広いprefix
    const arr = [...set].filter(x => x !== String(h));
    return arr.slice(0, 3);
  },

  gameOver() {
    this.running = false;
    clearInterval(this.timer);
    document.getElementById("rush-play").classList.add("hidden");
    const over = document.getElementById("rush-over");
    over.classList.remove("hidden");
    const xp = this.score;
    addXP(xp);
    if (this.score > (S.rushBest || 0)) { S.rushBest = this.score; }
    save();
    document.getElementById("rush-final").textContent = `スコア ${this.score}`;
    document.getElementById("rush-detail").textContent =
      `正解 ${this.correct} 問 / 最高コンボ到達Lv.${this.level} / +${xp} XP  (自己ベスト: ${S.rushBest})`;
    renderStats(); renderHUD();
  },

  quit() { this.running = false; clearInterval(this.timer); go("home"); },
};

function rnd(n) { return Math.floor(Math.random() * n); }
function flash(msg) { popCombo(msg); }
