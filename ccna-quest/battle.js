/* =====================================================================
 * CCNA Quest - アドベンチャー / バトルエンジン (ポケモン風RPG)
 * パケットンを操作し、分野ごとのモンスターと問題で戦う。
 * 正解=攻撃 / 不正解・時間切れ=被ダメージ。素早い正解でクリティカル。
 * ===================================================================== */

/* 章 = CCNAの6分野。各章は複数の雑魚戦 + ボス戦。 */
const CHAPTERS = [
  { id: "fundamentals", title: "第1章 ネットワークの森",     mobs: ["collision", "vlan"], boss: "loop",       bossName: "ループ・ゴースト" },
  { id: "access",       title: "第2章 スイッチング洞窟",     mobs: ["vlan", "collision"], boss: "loop",       bossName: "ストーム・ロード" },
  { id: "connectivity", title: "第3章 ルーティング山脈",     mobs: ["routing", "vlan"],   boss: "routing",    bossName: "ゴーレム・キング" },
  { id: "services",     title: "第4章 サービスの街",         mobs: ["automation", "routing"], boss: "routing", bossName: "NATタイタン" },
  { id: "security",     title: "第5章 セキュリティ要塞",     mobs: ["security", "loop"],  boss: "security",   bossName: "セキュリティ・リーパー" },
  { id: "automation",   title: "第6章 自動化ラボ",           mobs: ["automation", "security"], boss: "dragon", bossName: "サブネット・ドラゴン" },
];

const Adventure = {
  renderMap() {
    const prog = S.adventure;
    const wrap = document.getElementById("adv-map");
    wrap.innerHTML = "";
    CHAPTERS.forEach((ch, ci) => {
      const stages = ch.mobs.length + 1; // 雑魚 + ボス
      const unlockedCh = ci <= prog.chapter;
      const card = document.createElement("div");
      card.className = "chapter" + (unlockedCh ? "" : " locked");
      let dots = "";
      for (let si = 0; si < stages; si++) {
        const cleared = ci < prog.chapter || (ci === prog.chapter && si < prog.stage);
        const current = ci === prog.chapter && si === prog.stage;
        const isBoss = si === stages - 1;
        dots += `<span class="stage-dot ${cleared ? "done" : current ? "cur" : ""} ${isBoss ? "boss" : ""}"
          title="${isBoss ? "ボス" : "ステージ" + (si + 1)}">${isBoss ? "👑" : cleared ? "✓" : si + 1}</span>`;
      }
      card.innerHTML = `<div class="ch-head"><b>${ch.title}</b>${unlockedCh ? "" : " 🔒"}</div>
        <div class="stage-row">${dots}</div>`;
      if (unlockedCh) card.onclick = () => this.enterChapter(ci);
      wrap.appendChild(card);
    });
    // HPアップグレード表示
    document.getElementById("adv-maxhp").textContent = 100 + (S.adventure.hpBonus || 0);
  },

  enterChapter(ci) {
    if (ci !== S.adventure.chapter) {
      // 既にクリア済みの章 → 復習として最初から
      S.adventure._replay = ci;
    } else {
      S.adventure._replay = null;
    }
    Battle.start(ci);
  },
};

const Battle = {
  hero: {}, enemy: {}, pool: [], q: null, timer: null, timeLeft: 0, timeMax: 8,
  chapterIdx: 0, stageIdx: 0, isBoss: false, combo: 0, busy: false,

  start(ci) {
    this.chapterIdx = ci;
    const replay = S.adventure._replay;
    this.stageIdx = (replay != null) ? 0 : S.adventure.stage;
    const ch = CHAPTERS[ci];
    // 問題プールをこの章の分野から用意(バトルは単一選択のみ)
    const single = q => !Array.isArray(q.answer);
    this.pool = shuffle(QUIZ_BANK.filter(x => x.domain === ch.id && single(x)));
    if (this.pool.length < 4) this.pool = this.pool.concat(shuffle(QUIZ_BANK.filter(single))); // 予備
    this._qi = 0;
    this.setupStage();
    go("battle");
  },

  setupStage() {
    const ch = CHAPTERS[this.chapterIdx];
    const stages = ch.mobs.length + 1;
    this.isBoss = this.stageIdx === stages - 1;
    const kind = this.isBoss ? ch.boss : ch.mobs[this.stageIdx];
    const info = Art.monster(kind);
    const maxHP = 100 + (S.adventure.hpBonus || 0);
    this.hero = { hp: maxHP, max: maxHP };
    const enemyHP = this.isBoss ? 130 : 70;
    this.enemy = { hp: enemyHP, max: enemyHP, name: this.isBoss ? ch.bossName : info.name, kind };
    this.combo = 0;
    this.timeMax = this.isBoss ? 7 : 9;

    document.getElementById("battle-chapter").textContent = ch.title +
      (this.isBoss ? " — ボス戦！" : ` — ステージ ${this.stageIdx + 1}`);
    document.getElementById("hero-sprite").innerHTML = Art.hero("normal");
    document.getElementById("enemy-sprite").innerHTML = info.svg;
    document.getElementById("enemy-name").textContent = this.enemy.name + (this.isBoss ? " 👑" : "");
    document.getElementById("battle-stage").classList.toggle("bossfight", this.isBoss);
    this.updateBars();
    this.nextQuestion();
  },

  updateBars() {
    const hp = document.getElementById("hero-hp");
    hp.style.width = Math.max(0, this.hero.hp / this.hero.max * 100) + "%";
    hp.className = "bar-fill hp" + (this.hero.hp / this.hero.max < 0.3 ? " low" : "");
    document.getElementById("hero-hp-txt").textContent = `${Math.max(0, Math.ceil(this.hero.hp))}/${this.hero.max}`;
    const ehp = document.getElementById("enemy-hp");
    ehp.style.width = Math.max(0, this.enemy.hp / this.enemy.max * 100) + "%";
    document.getElementById("enemy-hp-txt").textContent = `${Math.max(0, Math.ceil(this.enemy.hp))}/${this.enemy.max}`;
  },

  nextQuestion() {
    this.busy = false;
    if (this._qi >= this.pool.length) { this.pool = shuffle(this.pool); this._qi = 0; }
    const src = this.pool[this._qi++];
    const order = shuffle(src.choices.map((c, i) => i));
    this.q = { q: src.q, exp: src.exp, fig: src.fig,
      choices: order.map(i => src.choices[i]), answer: order.indexOf(src.answer) };

    document.getElementById("battle-fig").innerHTML = src.fig ? Art.diagram(src.fig) : "";
    document.getElementById("battle-q").textContent = this.q.q;
    const box = document.getElementById("battle-choices");
    box.innerHTML = "";
    this.q.choices.forEach((c, i) => {
      const b = document.createElement("button");
      b.className = "choice";
      b.innerHTML = `<span>${c}</span>`;
      b.onclick = () => this.answer(i, b);
      box.appendChild(b);
    });
    document.getElementById("battle-exp").className = "exp";
    this.startTimer();
  },

  startTimer() {
    this.timeLeft = this.timeMax;
    const bar = document.getElementById("time-bar");
    bar.style.transition = "none";
    bar.style.width = "100%";
    // reflow then animate
    void bar.offsetWidth;
    bar.style.transition = `width ${this.timeMax}s linear`;
    bar.style.width = "0%";
    clearInterval(this.timer);
    const t0 = Date.now();
    this.timer = setInterval(() => {
      this.timeLeft = this.timeMax - (Date.now() - t0) / 1000;
      if (this.timeLeft <= 0) { this.timeUp(); }
    }, 100);
  },
  stopTimer() { clearInterval(this.timer); },

  timeUp() {
    if (this.busy) return;
    this.busy = true;
    this.stopTimer();
    [...document.querySelectorAll("#battle-choices .choice")].forEach(b => b.disabled = true);
    document.querySelectorAll("#battle-choices .choice")[this.q.answer].classList.add("correct");
    this.combo = 0;
    const exp = document.getElementById("battle-exp");
    exp.className = "exp ng show";
    exp.innerHTML = `<span class="tag">⏰ 時間切れ！</span>${this.q.exp}`;
    this.enemyAttack(14);
  },

  answer(pick, btn) {
    if (this.busy) return;
    this.busy = true;
    this.stopTimer();
    const buttons = [...document.querySelectorAll("#battle-choices .choice")];
    buttons.forEach(b => b.disabled = true);
    const exp = document.getElementById("battle-exp");

    if (pick === this.q.answer) {
      btn.classList.add("correct");
      this.combo += 1;
      const fast = this.timeLeft > this.timeMax * 0.55;
      const crit = fast && Math.random() < 0.5;
      let dmg = 18 + this.combo * 2 + Math.round(this.timeLeft);
      if (crit) dmg = Math.round(dmg * 1.8);
      this.heroAttack(dmg, crit);
      exp.className = "exp ok show";
      exp.innerHTML = `<span class="tag">${crit ? "⚡クリティカル！ " : "正解！ "}${dmg} ダメージ</span>${this.q.exp}`;
    } else {
      btn.classList.add("wrong");
      buttons[this.q.answer].classList.add("correct");
      this.combo = 0;
      exp.className = "exp ng show";
      exp.innerHTML = `<span class="tag">ミス！</span>${this.q.exp}`;
      this.enemyAttack(16);
    }
  },

  heroAttack(dmg, crit) {
    document.getElementById("hero-sprite").innerHTML = Art.hero("attack");
    const es = document.getElementById("enemy-sprite");
    es.classList.add("shake");
    this.floatDmg(es, dmg, crit ? "crit" : "");
    this.enemy.hp -= dmg;
    setTimeout(() => {
      es.classList.remove("shake");
      document.getElementById("hero-sprite").innerHTML = Art.hero("normal");
      this.updateBars();
      if (this.enemy.hp <= 0) this.win();
      else this.showNext();
    }, 650);
  },

  enemyAttack(dmg) {
    setTimeout(() => {
      const hs = document.getElementById("hero-sprite");
      hs.classList.add("shake");
      hs.innerHTML = Art.hero("hurt");
      this.floatDmg(hs, dmg, "enemy");
      this.hero.hp -= dmg;
      setTimeout(() => {
        hs.classList.remove("shake");
        this.updateBars();
        if (this.hero.hp <= 0) this.lose();
        else { hs.innerHTML = Art.hero("normal"); this.showNext(); }
      }, 650);
    }, 300);
  },

  floatDmg(container, dmg, cls) {
    const d = document.createElement("div");
    d.className = "dmg " + cls;
    d.textContent = (cls === "enemy" ? "-" : "") + dmg + (cls === "crit" ? "!" : "");
    container.appendChild(d);
    setTimeout(() => d.remove(), 900);
  },

  showNext() {
    const row = document.getElementById("battle-next-row");
    row.classList.remove("hidden");
    document.getElementById("battle-next").onclick = () => { row.classList.add("hidden"); this.nextQuestion(); };
  },

  win() {
    this.stopTimer();
    document.getElementById("enemy-sprite").classList.add("defeated");
    const xp = this.isBoss ? 120 : 45;
    setTimeout(() => {
      addXP(xp);
      // 進行状況を更新(通常プレイのみ前進、リプレイは前進しない)
      if (S.adventure._replay == null) {
        const ch = CHAPTERS[this.chapterIdx];
        const stages = ch.mobs.length + 1;
        if (this.stageIdx + 1 >= stages) {
          // 章クリア
          S.adventure.chapter = Math.min(CHAPTERS.length, this.chapterIdx + 1);
          S.adventure.stage = 0;
          S.adventure.hpBonus = (S.adventure.hpBonus || 0) + 10; // ごほうび: 最大HP+10
          if (!S.domainsCleared.includes(ch.id)) S.domainsCleared.push(ch.id);
          if (S.adventure.chapter >= CHAPTERS.length) unlock("adv_clear");
        } else {
          S.adventure.stage += 1;
        }
        save();
      }
      document.getElementById("enemy-sprite").classList.remove("defeated");
      this.resultScreen(true, xp);
    }, 800);
  },

  lose() {
    this.stopTimer();
    this.resultScreen(false, 0);
  },

  resultScreen(won, xp) {
    document.getElementById("res-emoji").textContent = won ? (this.isBoss ? "👑" : "⚔️") : "💀";
    document.getElementById("res-score").textContent = won ? "バトル勝利！" : "たおれてしまった…";
    document.getElementById("res-xp").textContent = won ? `+${xp} XP` : "";
    document.getElementById("res-msg").textContent = won
      ? (this.isBoss ? "ボス撃破！次の章が解放されました。最大HPも増えました。" : "次のステージへ進もう！")
      : "解説を読んで再挑戦しよう。焦らず素早く正解するのがコツ。";
    document.getElementById("res-again").textContent = won ? "冒険を続ける" : "もう一度挑戦";
    document.getElementById("res-again").onclick = () => { Adventure.renderMap(); go("adventure"); };
    renderStats(); renderHUD();
    go("result");
  },

  quit() { if (confirm("バトルを中断しますか？(進行状況はステージ単位で保存されます)")) { this.stopTimer(); Adventure.renderMap(); go("adventure"); } },
};
