/* =====================================================================
 * CCNA Quest - キャラクター立ち絵ジェネレータ (アニメ風SVG)
 * Art.face(style, mood) : プロフィール写真・チャット・デートで使用
 *   style = { skin, hair, hair2, eyes, hairstyle, accessory, outfit }
 *   mood  = normal | happy | shy | sad | annoyed | love | surprised
 * すべてインラインSVGで描画（外部画像なし / CSP安全）。
 * ===================================================================== */

Art.face = function (style, mood = "normal", opts = {}) {
  const s = Object.assign({
    skin: "#ffe0d0", hair: "#5b4636", hair2: "#3f3025", eyes: "#6b4a2b",
    hairstyle: "long", accessory: null, outfit: "#64748b",
  }, style || {});
  const bg = opts.bg || null; // 円背景色(プロフ写真用)

  // ---- 表情パーツ ----
  const brows = {
    normal:    `<path d="M64 92 q10 -5 20 -1" stroke="#7a5c48" stroke-width="3" fill="none" stroke-linecap="round"/>
                <path d="M116 91 q10 -4 20 1" stroke="#7a5c48" stroke-width="3" fill="none" stroke-linecap="round"/>`,
    happy:     `<path d="M64 88 q10 -6 20 -2" stroke="#7a5c48" stroke-width="3" fill="none" stroke-linecap="round"/>
                <path d="M116 86 q10 -4 20 2" stroke="#7a5c48" stroke-width="3" fill="none" stroke-linecap="round"/>`,
    shy:       `<path d="M64 90 q10 -4 20 -1" stroke="#7a5c48" stroke-width="3" fill="none" stroke-linecap="round"/>
                <path d="M116 89 q10 -3 20 1" stroke="#7a5c48" stroke-width="3" fill="none" stroke-linecap="round"/>`,
    sad:       `<path d="M64 88 q12 4 20 8" stroke="#7a5c48" stroke-width="3" fill="none" stroke-linecap="round"/>
                <path d="M116 96 q8 -4 20 -8" stroke="#7a5c48" stroke-width="3" fill="none" stroke-linecap="round"/>`,
    annoyed:   `<path d="M64 86 q12 6 20 9" stroke="#7a5c48" stroke-width="3.5" fill="none" stroke-linecap="round"/>
                <path d="M116 95 q8 -3 20 -9" stroke="#7a5c48" stroke-width="3.5" fill="none" stroke-linecap="round"/>`,
    love:      `<path d="M64 87 q10 -6 20 -2" stroke="#7a5c48" stroke-width="3" fill="none" stroke-linecap="round"/>
                <path d="M116 85 q10 -4 20 2" stroke="#7a5c48" stroke-width="3" fill="none" stroke-linecap="round"/>`,
    surprised: `<path d="M64 84 q10 -3 20 0" stroke="#7a5c48" stroke-width="3" fill="none" stroke-linecap="round"/>
                <path d="M116 84 q10 -2 20 1" stroke="#7a5c48" stroke-width="3" fill="none" stroke-linecap="round"/>`,
  }[mood] || "";

  const eye = (cx) => {
    const ir = s.eyes;
    if (mood === "happy") // ^_^ 閉じ目
      return `<path d="M${cx - 12} 112 q12 -12 24 0" stroke="#3a2a20" stroke-width="3.5" fill="none" stroke-linecap="round"/>`;
    if (mood === "love") // ハート目
      return `<g><circle cx="${cx}" cy="110" r="13" fill="#fff"/>
        <path d="M${cx} 116 l-8 -8 a4.5 4.5 0 0 1 8 -1 a4.5 4.5 0 0 1 8 1 z" fill="#ff5c8a"/>
        <circle cx="${cx - 3}" cy="106" r="2" fill="#fff"/></g>`;
    if (mood === "shy") // 半目
      return `<g><path d="M${cx - 13} 108 q13 -8 26 0 q-3 10 -13 10 q-10 0 -13 -10z" fill="#fff" stroke="#3a2a20" stroke-width="1.5"/>
        <circle cx="${cx}" cy="112" r="8" fill="${ir}"/><circle cx="${cx}" cy="112" r="4" fill="#241a13"/>
        <circle cx="${cx - 3}" cy="109" r="2.4" fill="#fff"/>
        <path d="M${cx - 13} 108 q13 -8 26 0" stroke="#3a2a20" stroke-width="2.5" fill="none"/></g>`;
    const wide = mood === "surprised";
    const ry = wide ? 18 : 15;
    const cy = wide ? 108 : 111;
    const irr = wide ? 9.5 : 10.5;   // 大きめの瞳(ギャル/かわいい系)
    const gid = "ir" + (Art._fid = (Art._fid || 0) + 1);
    return `<g>
      <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${ir}"/><stop offset="1" stop-color="${shade(ir)}"/></linearGradient></defs>
      <ellipse cx="${cx}" cy="110" rx="13" ry="${ry}" fill="#fff"/>
      <circle cx="${cx}" cy="${cy}" r="${irr}" fill="url(#${gid})"/>
      <circle cx="${cx}" cy="${cy + 1}" r="${wide ? 4.5 : 5.5}" fill="#20140d"/>
      <ellipse cx="${cx}" cy="${cy + 7}" rx="8" ry="4" fill="#fff" opacity=".25"/>
      <circle cx="${cx - 3.5}" cy="${cy - 4}" r="3.4" fill="#fff"/>
      <circle cx="${cx + 3.5}" cy="${cy + 4}" r="2" fill="#fff" opacity=".9"/>
      <path d="M${cx - 14} 99 q14 -7 28 0" stroke="#2a1c14" stroke-width="4" fill="none" stroke-linecap="round"/>
      <path d="M${cx + 10} 98 l6 -4" stroke="#2a1c14" stroke-width="3" fill="none" stroke-linecap="round"/>
      <path d="M${cx - 14} 121 q6 4 11 4" stroke="#2a1c14" stroke-width="1.6" fill="none" stroke-linecap="round" opacity=".6"/></g>`;
  };
  const shade = (hex) => { // 瞳の下側を少し暗く
    const n = parseInt(hex.slice(1), 16);
    const r = Math.max(0, (n >> 16 & 255) - 40), g = Math.max(0, (n >> 8 & 255) - 40), b = Math.max(0, (n & 255) - 30);
    return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
  };

  const mouth = {
    normal:    `<path d="M92 148 q8 6 16 0" stroke="#b5566a" stroke-width="2.5" fill="none" stroke-linecap="round"/>`,
    happy:     `<path d="M88 145 q12 16 24 0 z" fill="#c1465f" stroke="#a83a52" stroke-width="1.5"/><path d="M90 147 q10 5 20 0" fill="#ff9ba8"/>`,
    shy:       `<path d="M94 149 q6 4 12 0" stroke="#b5566a" stroke-width="2.5" fill="none" stroke-linecap="round"/>`,
    sad:       `<path d="M92 152 q8 -6 16 0" stroke="#b5566a" stroke-width="2.5" fill="none" stroke-linecap="round"/>`,
    annoyed:   `<path d="M92 150 h16" stroke="#b5566a" stroke-width="2.5" fill="none" stroke-linecap="round"/>`,
    love:      `<path d="M92 147 q8 8 16 0" stroke="#c1465f" stroke-width="2.5" fill="none" stroke-linecap="round"/>`,
    surprised: `<ellipse cx="100" cy="150" rx="6" ry="8" fill="#a83a52"/>`,
  }[mood] || "";

  const blush = (["shy", "love", "happy"].includes(mood))
    ? `<ellipse cx="70" cy="132" rx="11" ry="6" fill="#ff9a9a" opacity="${mood === "love" ? .75 : .55}"/>
       <ellipse cx="130" cy="132" rx="11" ry="6" fill="#ff9a9a" opacity="${mood === "love" ? .75 : .55}"/>`
    : "";

  // ---- 髪型 (背面 + 前髪) ----
  const H = hairShapes(s.hairstyle, s.hair, s.hair2);

  // ---- アクセサリ ----
  let acc = "";
  if (s.accessory === "glasses")
    acc = `<g fill="none" stroke="#334155" stroke-width="2.5"><rect x="60" y="98" width="30" height="24" rx="8"/><rect x="110" y="98" width="30" height="24" rx="8"/><path d="M90 108 h20"/></g>`;
  else if (s.accessory === "clip")
    acc = `<g><rect x="60" y="70" width="16" height="7" rx="3" fill="#ff5c8a"/><circle cx="68" cy="73" r="2" fill="#fff"/></g>`;
  else if (s.accessory === "headset")
    acc = `<path d="M52 108 q0 -56 96 0" fill="none" stroke="#1e293b" stroke-width="5"/><rect x="44" y="104" width="12" height="18" rx="5" fill="#1e293b"/><rect x="144" y="104" width="12" height="18" rx="5" fill="#38bdf8"/>`;
  else if (s.accessory === "star")
    acc = `<path d="M64 72 l3 6 6 1 -4 5 1 6 -6 -3 -6 3 1 -6 -4 -5 6 -1z" fill="#fde047"/>`;

  const surprise = mood === "surprised" ? `<text x="150" y="70" font-size="26">💦</text>` : "";
  const love = mood === "love" ? `<text x="150" y="72" font-size="22">💕</text>` : "";

  return `<svg viewBox="0 0 200 220" class="face" preserveAspectRatio="xMidYMid meet" aria-label="キャラクター">
    ${bg ? `<circle cx="100" cy="110" r="108" fill="${bg}"/>` : ""}
    <g class="face-bob">
      ${H.back}
      <path d="M70 168 q30 -10 60 0 l6 40 h-72 z" fill="${s.outfit}"/>
      <rect x="86" y="158" width="28" height="20" rx="8" fill="${s.skin}"/>
      <path d="M48 96 C48 58 152 58 152 96 C152 152 122 178 100 178 C78 178 48 152 48 96 Z" fill="${s.skin}"/>
      <ellipse cx="49" cy="116" rx="7" ry="10" fill="${s.skin}"/><ellipse cx="151" cy="116" rx="7" ry="10" fill="${s.skin}"/>
      ${H.front}
      ${brows}
      ${eye(76)}${eye(124)}
      <path d="M99 124 q3 5 -1 8" stroke="#e0a894" stroke-width="2" fill="none" stroke-linecap="round"/>
      ${blush}
      ${mouth}
      ${acc}
      ${surprise}${love}
    </g>
  </svg>`;
};

/* 髪型シェイプ集 */
function hairShapes(kind, c, c2) {
  const shade = c2 || c;
  const S = {
    long: {
      back: `<path d="M40 150 C24 90 40 40 100 40 C160 40 176 90 160 150 L160 200 L148 200 C150 130 150 96 150 96 L50 96 C50 96 50 130 52 200 L40 200 Z" fill="${shade}"/>`,
      front: `<path d="M44 100 C40 52 70 34 100 34 C132 34 162 54 156 102 C150 78 140 70 128 68 C120 84 108 88 100 88 C92 88 82 84 74 70 C60 76 50 86 44 100 Z" fill="${c}"/>
              <path d="M100 34 C86 34 70 44 66 66 q18 -12 34 -10 z" fill="${shade}" opacity=".5"/>`,
    },
    twin: {
      back: `<path d="M46 92 C42 50 70 40 100 40 C130 40 158 50 154 92 L146 92 C146 70 130 60 100 60 C70 60 54 70 54 92 Z" fill="${shade}"/>
             <ellipse cx="34" cy="132" rx="18" ry="34" fill="${shade}"/><ellipse cx="166" cy="132" rx="18" ry="34" fill="${shade}"/>
             <circle cx="40" cy="96" r="9" fill="${c}"/><circle cx="160" cy="96" r="9" fill="${c}"/>`,
      front: `<path d="M46 100 C42 50 72 34 100 34 C130 34 160 52 154 102 C148 80 138 72 126 70 C118 84 108 88 100 88 C92 88 82 84 74 70 C60 76 52 86 46 100 Z" fill="${c}"/>`,
    },
    bob: {
      back: `<path d="M44 140 C36 84 52 42 100 42 C148 42 164 84 156 140 L156 150 C156 120 150 100 150 100 L50 100 C50 100 44 120 44 150 Z" fill="${shade}"/>`,
      front: `<path d="M44 108 C40 56 70 36 100 36 C130 36 160 56 156 108 C150 84 140 74 128 72 C118 88 108 90 100 90 C92 90 80 86 72 72 C60 78 50 90 44 108 Z" fill="${c}"/>`,
    },
    pony: {
      back: `<path d="M150 60 C176 70 184 120 168 168 C160 150 150 120 146 96 Z" fill="${shade}"/>
             <path d="M46 130 C40 80 56 42 100 42 C150 42 158 78 150 96 L52 96 C50 108 48 120 48 130 Z" fill="${shade}"/>`,
      front: `<path d="M44 104 C40 54 72 36 100 36 C138 36 164 58 156 100 C150 78 138 70 126 68 C116 84 106 88 96 86 C88 84 80 80 74 70 C60 76 50 88 44 104 Z" fill="${c}"/>`,
    },
    short: {
      back: `<path d="M48 120 C44 78 58 44 100 44 C142 44 156 78 152 120 L152 112 C152 96 150 96 150 96 L50 96 C50 96 48 96 48 112 Z" fill="${shade}"/>`,
      front: `<path d="M46 104 C42 58 70 38 100 38 C130 38 158 58 154 104 C146 82 132 74 118 74 C112 84 106 86 100 86 C92 86 84 82 78 72 C62 78 52 88 46 104 Z" fill="${c}"/>`,
    },
    wavy: {
      back: `<path d="M38 150 C22 88 40 40 100 40 C160 40 178 88 162 150 C158 176 150 176 150 196 C146 178 152 160 150 150 C150 130 150 96 150 96 L50 96 C50 130 50 150 50 150 C48 160 54 178 50 196 C50 176 42 176 38 150 Z" fill="${shade}"/>`,
      front: `<path d="M44 102 C40 52 70 34 100 34 C132 34 162 54 156 104 C150 80 140 72 128 70 C122 82 116 74 108 78 C102 88 96 82 92 76 C84 84 80 74 74 70 C60 76 50 84 44 102 Z" fill="${c}"/>`,
    },
  };
  return S[kind] || S.long;
}
