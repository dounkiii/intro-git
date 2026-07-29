/* =====================================================================
 * CCNA Quest - 模擬試験モード (本番形式)
 * ・分野の比率に沿って出題 ・制限時間つき ・リニア形式(戻れない)
 * ・複数選択対応 ・300〜1000のスケール換算で合否判定(合格ラインは目安)
 * ===================================================================== */

const Exam = {
  queue: [], idx: 0, answers: [], startTime: 0, minutes: 20, timer: null, count: 25,

  setup() {
    document.getElementById("exam-facts").innerHTML = `
      <li>本番: ${EXAM_FACTS.questionsReal}・${EXAM_FACTS.minutesReal}分</li>
      <li>${EXAM_FACTS.style}</li>
      <li>${EXAM_FACTS.passNote}</li>
      <li class="muted">※このモードは短縮版です。合格ラインは目安値です。</li>`;
    go("exam-setup");
  },

  start() {
    this.count = parseInt(document.getElementById("exam-count").value, 10);
    this.minutes = this.count <= 15 ? 12 : this.count <= 25 ? 20 : 40;
    // 分野の比率に沿って抽出
    this.queue = this.buildSet(this.count);
    this.idx = 0;
    this.answers = [];
    this.startTime = Date.now();
    touchStreak();
    go("exam");
    this.startTimer();
    this.render();
  },

  buildSet(n) {
    const set = [];
    const totalW = CCNA_DOMAINS.reduce((a, d) => a + d.weight, 0);
    CCNA_DOMAINS.forEach(d => {
      const take = Math.max(1, Math.round(n * d.weight / totalW));
      const pool = shuffle(QUIZ_BANK.filter(q => q.domain === d.id));
      set.push(...pool.slice(0, take));
    });
    // 件数調整
    let result = shuffle(set);
    if (result.length > n) result = result.slice(0, n);
    while (result.length < n) {
      const extra = shuffle(QUIZ_BANK).find(q => !result.includes(q));
      if (!extra) break; result.push(extra);
    }
    // 選択肢シャッフル
    return result.map(q => {
      const order = shuffle(q.choices.map((c, i) => i));
      const ansArr = (Array.isArray(q.answer) ? q.answer : [q.answer]).map(a => order.indexOf(a));
      return { domain: q.domain, diff: q.diff, q: q.q, exp: q.exp, fig: q.fig,
        choices: order.map(i => q.choices[i]), answer: ansArr, multi: Array.isArray(q.answer) };
    });
  },

  startTimer() {
    clearInterval(this.timer);
    this.timer = setInterval(() => {
      const elapsed = (Date.now() - this.startTime) / 1000;
      const left = this.minutes * 60 - elapsed;
      if (left <= 0) { this.finish(); return; }
      const m = Math.floor(left / 60), s = Math.floor(left % 60);
      const el = document.getElementById("exam-timer");
      el.textContent = `${m}:${String(s).padStart(2, "0")}`;
      el.classList.toggle("danger", left < 60);
    }, 500);
  },

  render() {
    const item = this.queue[this.idx];
    document.getElementById("exam-progress").textContent = `第 ${this.idx + 1} / ${this.queue.length} 問`;
    document.getElementById("exam-bar").style.width = (this.idx / this.queue.length * 100) + "%";
    document.getElementById("exam-dom").textContent =
      `${domainName(item.domain)}・${DIFF_LABELS[item.diff]}`;
    document.getElementById("exam-multi").classList.toggle("hidden", !item.multi);
    document.getElementById("exam-fig").innerHTML = item.fig ? Art.diagram(item.fig) : "";
    document.getElementById("exam-q").textContent = item.q;

    this._picked = new Set();
    const box = document.getElementById("exam-choices");
    box.innerHTML = "";
    const keys = ["A", "B", "C", "D", "E"];
    item.choices.forEach((c, i) => {
      const b = document.createElement("button");
      b.className = "choice";
      b.innerHTML = `<span class="key">${keys[i]}</span><span>${c}</span>`;
      b.onclick = () => this.pick(i, b, item.multi);
      box.appendChild(b);
    });
    const btn = document.getElementById("exam-submit");
    btn.textContent = this.idx + 1 < this.queue.length ? "回答して次へ →" : "回答して採点";
    btn.disabled = true;
  },

  pick(i, btn, multi) {
    if (multi) {
      if (this._picked.has(i)) { this._picked.delete(i); btn.classList.remove("sel"); }
      else { this._picked.add(i); btn.classList.add("sel"); }
    } else {
      this._picked = new Set([i]);
      [...document.querySelectorAll("#exam-choices .choice")].forEach(b => b.classList.remove("sel"));
      btn.classList.add("sel");
    }
    document.getElementById("exam-submit").disabled = this._picked.size === 0;
  },

  submit() {
    const item = this.queue[this.idx];
    const picked = [...this._picked].sort();
    const correct = item.answer.slice().sort();
    const isCorrect = picked.length === correct.length && picked.every((v, k) => v === correct[k]);
    this.answers.push({ item, picked, isCorrect });
    this.idx += 1;
    if (this.idx < this.queue.length) this.render();
    else this.finish();
  },

  finish() {
    clearInterval(this.timer);
    const total = this.queue.length;
    const answered = this.answers.length;
    const correctN = this.answers.filter(a => a.isCorrect).length;
    // 300〜1000スケール換算
    const ratio = total ? correctN / total : 0;
    const scaled = Math.round(300 + ratio * 700);
    const passMark = 825;
    const passed = scaled >= passMark;
    if (passed) unlock("exam_pass");

    // 分野別集計
    const dom = {};
    CCNA_DOMAINS.forEach(d => dom[d.id] = { c: 0, t: 0 });
    this.answers.forEach(a => { dom[a.item.domain].t++; if (a.isCorrect) dom[a.item.domain].c++; });

    S.examTaken = (S.examTaken || 0) + 1;
    if (scaled > (S.examBest || 0)) S.examBest = scaled;
    addXP(50 + correctN * 5);
    save();

    const wrap = document.getElementById("exam-result-body");
    wrap.innerHTML = `
      <div class="exam-score ${passed ? "pass" : "fail"}">
        <div class="scaled">${scaled}<small>/1000</small></div>
        <div class="verdict">${passed ? "合格ライン到達 🎉" : "合格ラインまであと少し"}</div>
        <div class="muted">正答 ${correctN}/${total}(未回答は不正解扱い)・合格目安 ${passMark}</div>
      </div>
      <h4>分野別スコア</h4>
      <div class="dombars">
        ${CCNA_DOMAINS.map(d => {
          const x = dom[d.id]; const p = x.t ? Math.round(x.c / x.t * 100) : 0;
          return `<div class="dombar"><span class="dl">${d.icon} ${d.name}</span>
            <span class="dt"><span class="df" style="width:${p}%;background:${d.color}"></span></span>
            <span class="dv">${x.c}/${x.t}</span></div>`;
        }).join("")}
      </div>
      <h4>復習(間違えた問題)</h4>
      <div class="review">
        ${this.answers.filter(a => !a.isCorrect).map(a => `
          <div class="rev-item">
            <div class="rev-q">${a.item.q}</div>
            <div class="rev-a">正解: ${a.item.answer.map(i => a.item.choices[i]).join(" / ")}</div>
            <div class="muted">${a.item.exp}</div>
          </div>`).join("") || "<p class='muted'>全問正解！完璧です。</p>"}
      </div>`;
    document.getElementById("exam-best").textContent = S.examBest || scaled;
    renderStats(); renderHUD();
    go("exam-result");
  },

  quit() { if (confirm("模擬試験を中断しますか？(採点されません)")) { clearInterval(this.timer); go("home"); } },
};
