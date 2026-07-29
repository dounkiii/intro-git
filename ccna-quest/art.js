/* =====================================================================
 * CCNA Quest - アート (SVGキャラクター & 図解)
 * すべてインラインSVGで描画。外部画像は使いません(CSP安全)。
 * ===================================================================== */

const Art = {

  /* ---- ヒーロー: パケットン (データパケットの精霊) ---- */
  hero(mood = "normal") {
    // mood: normal / attack / hurt / happy
    const eye = mood === "hurt" ? "M34 46 l8 8 M42 46 l-8 8 M58 46 l8 8 M66 46 l-8 8"
      : null;
    const mouth = mood === "happy" ? "M38 62 q12 14 24 0"
      : mood === "hurt" ? "M40 66 q10 -8 20 0"
      : mood === "attack" ? "M40 60 h20 v6 h-20 z"
      : "M42 62 q8 6 16 0";
    return `<svg viewBox="0 0 100 100" class="sprite hero ${mood}" aria-label="パケットン">
      <defs>
        <linearGradient id="pkt" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#7dd3fc"/><stop offset="1" stop-color="#0ea5e9"/>
        </linearGradient>
      </defs>
      <g class="bob">
        <rect x="20" y="24" width="60" height="52" rx="14" fill="url(#pkt)" stroke="#0b4a6f" stroke-width="3"/>
        <path d="M20 30 L50 52 L80 30" fill="none" stroke="#e0f2fe" stroke-width="4" stroke-linecap="round"/>
        <rect x="16" y="66" width="12" height="14" rx="4" fill="#0284c7"/>
        <rect x="72" y="66" width="12" height="14" rx="4" fill="#0284c7"/>
        ${eye
          ? `<path d="${eye}" stroke="#083344" stroke-width="3.5" stroke-linecap="round" fill="none"/>`
          : `<circle cx="38" cy="50" r="6" fill="#083344"/><circle cx="62" cy="50" r="6" fill="#083344"/>
             <circle cx="40" cy="48" r="2" fill="#fff"/><circle cx="64" cy="48" r="2" fill="#fff"/>`}
        <path d="${mouth}" fill="${mood === "attack" ? "#083344" : "none"}" stroke="#083344" stroke-width="3" stroke-linecap="round"/>
        <circle cx="28" cy="58" r="3.5" fill="#fca5a5" opacity=".7"/>
        <circle cx="72" cy="58" r="3.5" fill="#fca5a5" opacity=".7"/>
      </g>
    </svg>`;
  },

  /* ---- 敵モンスター ---- */
  monster(kind) {
    const M = {
      collision: { // コリジョン・スライム
        name: "コリジョン・スライム", c1: "#fb923c", c2: "#c2410c",
        body: `<path d="M18 76 q0 -40 32 -40 q32 0 32 40 q-16 8 -32 8 q-16 0 -32 -8z" fill="var(--c1)" stroke="var(--c2)" stroke-width="3"/>
               <circle cx="40" cy="56" r="6" fill="#fff"/><circle cx="60" cy="56" r="6" fill="#fff"/>
               <circle cx="41" cy="57" r="3" fill="#000"/><circle cx="61" cy="57" r="3" fill="#000"/>
               <path d="M42 68 q8 6 16 0" stroke="#7c2d12" stroke-width="2.5" fill="none"/>`,
      },
      loop: { // ループ・ゴースト (STP/ブロードキャストストーム)
        name: "ループ・ゴースト", c1: "#a78bfa", c2: "#6d28d9",
        body: `<path d="M24 40 q26 -22 52 0 v34 l-8 -8 -8 8 -8 -8 -8 8 -8 -8 -8 8z" fill="var(--c1)" stroke="var(--c2)" stroke-width="3" opacity=".92"/>
               <circle cx="40" cy="48" r="5" fill="#1e1b4b"/><circle cx="60" cy="48" r="5" fill="#1e1b4b"/>
               <path d="M36 32 a14 14 0 1 1 28 0" fill="none" stroke="#ede9fe" stroke-width="3" stroke-dasharray="4 4"/>`,
      },
      vlan: { // VLANコウモリ
        name: "VLANコウモリ", c1: "#34d399", c2: "#047857",
        body: `<path d="M10 44 q18 -6 26 6 q6 -14 14 -14 q8 0 14 14 q8 -12 26 -6 q-14 8 -22 4 q6 12 -18 22 q-24 -10 -18 -22 q-8 4 -22 -4z" fill="var(--c1)" stroke="var(--c2)" stroke-width="3"/>
               <circle cx="44" cy="42" r="4" fill="#052e16"/><circle cx="56" cy="42" r="4" fill="#052e16"/>
               <path d="M46 50 l4 4 4 -4" stroke="#052e16" stroke-width="2" fill="none"/>`,
      },
      routing: { // ルーティング・ゴーレム
        name: "ルーティング・ゴーレム", c1: "#94a3b8", c2: "#475569",
        body: `<rect x="26" y="34" width="48" height="46" rx="6" fill="var(--c1)" stroke="var(--c2)" stroke-width="3"/>
               <rect x="34" y="26" width="32" height="12" rx="3" fill="var(--c2)"/>
               <rect x="36" y="46" width="12" height="12" rx="2" fill="#fbbf24"/>
               <rect x="52" y="46" width="12" height="12" rx="2" fill="#fbbf24"/>
               <rect x="38" y="49" width="8" height="6" fill="#1e293b"/><rect x="54" y="49" width="8" height="6" fill="#1e293b"/>
               <rect x="38" y="66" width="24" height="5" rx="2" fill="#334155"/>
               <rect x="18" y="42" width="8" height="24" rx="3" fill="var(--c2)"/><rect x="74" y="42" width="8" height="24" rx="3" fill="var(--c2)"/>`,
      },
      security: { // セキュリティ・リーパー
        name: "セキュリティ・リーパー", c1: "#f87171", c2: "#b91c1c",
        body: `<path d="M30 78 v-30 q0 -22 20 -22 q20 0 20 22 v30 z" fill="#1f2937" stroke="var(--c2)" stroke-width="3"/>
               <ellipse cx="50" cy="44" rx="16" ry="14" fill="var(--c1)"/>
               <circle cx="43" cy="44" r="4" fill="#450a0a"/><circle cx="57" cy="44" r="4" fill="#450a0a"/>
               <path d="M40 54 q10 6 20 0" stroke="#450a0a" stroke-width="2" fill="none"/>
               <path d="M50 20 l4 8 -8 0 z" fill="var(--c2)"/>`,
      },
      automation: { // オートメーション・ロボ
        name: "オートメーション・ロボ", c1: "#f472b6", c2: "#be185d",
        body: `<rect x="30" y="36" width="40" height="40" rx="8" fill="var(--c1)" stroke="var(--c2)" stroke-width="3"/>
               <circle cx="42" cy="52" r="6" fill="#fff"/><circle cx="58" cy="52" r="6" fill="#fff"/>
               <circle cx="42" cy="52" r="3" fill="#500724"/><circle cx="58" cy="52" r="3" fill="#500724"/>
               <rect x="40" y="64" width="20" height="5" rx="2" fill="#500724"/>
               <line x1="50" y1="36" x2="50" y2="24" stroke="var(--c2)" stroke-width="3"/><circle cx="50" cy="22" r="4" fill="#fde047"/>`,
      },
      dragon: { // ボス: サブネット・ドラゴン
        name: "サブネット・ドラゴン", c1: "#38bdf8", c2: "#1e40af", boss: true,
        body: `<path d="M22 70 q-10 -6 -6 -18 q8 4 10 10 q-6 -20 12 -30 q-4 -10 6 -14 q2 8 8 10 q10 -6 20 0 q8 4 10 16 q10 -6 16 2 q-8 2 -10 10 q8 8 4 24 q-10 -6 -16 -4 q-14 10 -30 4 q-8 4 -18 4z" fill="var(--c1)" stroke="var(--c2)" stroke-width="3"/>
               <circle cx="64" cy="38" r="6" fill="#fde047"/><circle cx="64" cy="38" r="3" fill="#1e293b"/>
               <path d="M52 30 l6 -10 4 8 z" fill="var(--c2)"/>
               <path d="M70 46 q8 2 10 8" stroke="#fff" stroke-width="2" fill="none"/>`,
      },
    };
    const m = M[kind] || M.collision;
    return {
      name: m.name,
      boss: !!m.boss,
      svg: `<svg viewBox="0 0 100 100" class="sprite monster${m.boss ? " boss" : ""}" style="--c1:${m.c1};--c2:${m.c2}" aria-label="${m.name}">
        <g class="float">${m.body}</g>
      </svg>`,
    };
  },

  /* ---- ネットワーク図 (問題用の図解) ---- */
  // トポロジ: 2ルータ + スイッチ + PC など、typeで切替
  diagram(type) {
    const D = {
      topo_router: `<svg viewBox="0 0 320 120" class="netdiagram" aria-label="ルータ間接続図">
        ${_router(40, 50, "R1")}${_router(240, 50, "R2")}
        <line x1="92" y1="66" x2="240" y2="66" stroke="#64748b" stroke-width="3"/>
        <text x="166" y="58" fill="#94a3b8" font-size="12" text-anchor="middle">WAN リンク</text>
        <text x="70" y="100" fill="#7dd3fc" font-size="11" text-anchor="middle">g0/0</text>
        <text x="262" y="100" fill="#7dd3fc" font-size="11" text-anchor="middle">g0/0</text>
      </svg>`,
      topo_lan: `<svg viewBox="0 0 340 150" class="netdiagram" aria-label="LAN構成図">
        ${_router(150, 12, "R1")}
        ${_switch(150, 70)}
        ${_pc(40, 118, "PC-A")}${_pc(150, 118, "PC-B")}${_pc(260, 118, "PC-C")}
        <line x1="172" y1="44" x2="172" y2="70" stroke="#64748b" stroke-width="2.5"/>
        <line x1="150" y1="92" x2="62" y2="118" stroke="#64748b" stroke-width="2"/>
        <line x1="172" y1="92" x2="172" y2="118" stroke="#64748b" stroke-width="2"/>
        <line x1="194" y1="92" x2="282" y2="118" stroke="#64748b" stroke-width="2"/>
      </svg>`,
      osi: `<svg viewBox="0 0 300 300" class="netdiagram osi" aria-label="OSI参照モデル">
        ${["7 アプリケーション","6 プレゼンテーション","5 セッション","4 トランスポート","3 ネットワーク","2 データリンク","1 物理"]
          .map((n, i) => `<g><rect x="30" y="${18 + i * 38}" width="240" height="32" rx="6" fill="${i < 3 ? "#334155" : i < 4 ? "#7c3aed" : i === 4 ? "#0891b2" : "#0f766e"}" stroke="#1e293b"/>
          <text x="150" y="${39 + i * 38}" fill="#e2e8f0" font-size="14" text-anchor="middle" font-weight="700">${n}</text></g>`).join("")}
      </svg>`,
    };
    return D[type] || "";
  },
};

/* ---- 図解パーツ ---- */
function _router(x, y, label) {
  return `<g transform="translate(${x},${y})">
    <rect x="0" y="0" width="52" height="32" rx="6" fill="#1e293b" stroke="#38bdf8" stroke-width="2"/>
    <path d="M10 16 h32 M32 8 l10 8 -10 8" stroke="#38bdf8" stroke-width="2" fill="none"/>
    <path d="M42 16 h-32 M20 8 l-10 8 10 8" stroke="#38bdf8" stroke-width="2" fill="none"/>
    <text x="26" y="46" fill="#e2e8f0" font-size="12" text-anchor="middle" font-weight="700">${label}</text>
  </g>`;
}
function _switch(x, y) {
  return `<g transform="translate(${x - 26},${y})">
    <rect x="0" y="0" width="52" height="24" rx="4" fill="#1e293b" stroke="#a78bfa" stroke-width="2"/>
    <path d="M8 12 h10 M18 6 l8 6 -8 6 M44 12 h-10 M34 6 l-8 6 8 6" stroke="#a78bfa" stroke-width="1.6" fill="none"/>
    <text x="26" y="-6" fill="#c4b5fd" font-size="11" text-anchor="middle" font-weight="700">SW1</text>
  </g>`;
}
function _pc(x, y, label) {
  return `<g transform="translate(${x - 20},${y - 20})">
    <rect x="0" y="0" width="40" height="26" rx="3" fill="#0f172a" stroke="#34d399" stroke-width="2"/>
    <rect x="14" y="26" width="12" height="4" fill="#34d399"/>
    <text x="20" y="18" fill="#6ee7b7" font-size="10" text-anchor="middle">🖥️</text>
    <text x="20" y="42" fill="#e2e8f0" font-size="10" text-anchor="middle" font-weight="700">${label}</text>
  </g>`;
}
