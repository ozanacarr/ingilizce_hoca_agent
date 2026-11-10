// Arayüz: sunucudan gelen öğretmen olaylarını 3D sınıfa ve panellere dağıtır,
// senin yazdıklarını ve söylediklerini sunucuya gönderir.
import { Classroom } from './classroom.js';
import { Mic, Voice } from './speech.js';

const $ = (id) => document.getElementById(id);
const SKILL_LABELS = { grammar: 'Dilbilgisi', vocabulary: 'Kelime', speaking: 'Konuşma', writing: 'Yazma', listening: 'Dinleme' };
const KIND_LABELS = { multiple_choice: 'Çoktan seçmeli', fill_blank: 'Boşluğu doldur', open: 'Serbest yazma', speak: 'Sesli cevap' };

let ws = null;
let classroom = null;
let streaming = false;
let activeQuestion = null;
let currentTeacherLog = null;
let correctionTimer = null;

// ---------------------------------------------------------------- ses
const voice = new Voice({ onSpeakingChange: () => updateTalking() });
const mic = new Mic({
  onInterim: (text) => { $('input').value = text; autoGrow(); },
  onFinal: (text) => { $('input').value = ''; autoGrow(); send(text, 'voice'); },
  onStateChange: (on) => $('mic-btn').classList.toggle('on', on),
});
if (!mic.supported) {
  $('mic-btn').disabled = true;
  $('mic-btn').title = 'Bu tarayıcı konuşmayı yazıya çeviremiyor. Chrome ya da Edge kullan.';
}

function updateTalking() {
  classroom?.setTalking(voice.speaking || streaming);
}

// ---------------------------------------------------------------- bağlantı
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  setStatus('bağlanıyor');
  ws.onopen = () => setStatus('bağlı');
  ws.onclose = () => setStatus('bağlantı koptu: sayfayı yenile', true);
  ws.onmessage = (e) => handleEvent(JSON.parse(e.data));
}

function setStatus(text, bad = false) {
  $('status').textContent = text;
  $('status').classList.toggle('bad', bad);
}

function send(text, via = 'text') {
  text = text.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
  if (activeQuestion && via === 'text') via = 'answer';
  ws.send(JSON.stringify({ type: 'student', text, via }));
  addLog('student', via === 'voice' ? '🎤 ' + text : text);
  hideQuestion();
  voice.stop();
}

// ---------------------------------------------------------------- olaylar
function handleEvent(ev) {
  switch (ev.type) {
    case 'hello': {
      const labels = {
        claude: [`CLAUDE ${(ev.plan || '').toUpperCase()}`.trim(), 'Öğretmen senin Claude hesabınla (Claude Code üzerinden) çalışıyor'],
        api: ['CANLI · API', 'Öğretmen Claude API anahtarıyla çalışıyor'],
        demo: ['DEMO', 'Hazır senaryolu demo ders: gerçek yapay zeka değil'],
      };
      const [label, title] = labels[ev.mode] || labels.demo;
      $('mode').textContent = label;
      $('mode').className = 'badge ' + (ev.mode === 'demo' ? 'demo' : 'live');
      $('mode').title = title;
      renderState(ev.state);
      break;
    }
    case 'thinking':
      classroom.setThinking(ev.on);
      if (ev.on) showBubble();
      $('dots').hidden = !ev.on;
      break;
    case 'say_start':
      streaming = true;
      updateTalking();
      $('dots').hidden = true;
      showBubble();
      $('bubble-text').textContent = '';
      currentTeacherLog = addLog('teacher', '');
      break;
    case 'say_delta':
      $('bubble-text').textContent += ev.text;
      if (currentTeacherLog) currentTeacherLog.querySelector('.text').textContent += ev.text;
      voice.feed(ev.text);
      scrollLog();
      break;
    case 'say_end':
      streaming = false;
      voice.flush();
      setTimeout(updateTalking, 300);
      break;
    case 'board':
      classroom.writeBoard(ev.title, ev.lines);
      if (ev.title) addLog('note', `Tahtaya yazdı: ${ev.title}`);
      break;
    case 'question':
      showQuestion(ev);
      break;
    case 'correction':
      showCorrection(ev);
      classroom.addCorrection(ev);
      addFixLog(ev);
      break;
    case 'vocab_added':
      toast(`📌 Yeni kelime: ${ev.word} (${ev.meaning_tr})`, 'word');
      addLog('note', `Kelime duvarı: ${ev.word} = ${ev.meaning_tr}. Örnek: ${ev.example}`);
      break;
    case 'xp':
      toast(`+${ev.amount} XP · ${ev.reason}`, 'xp');
      break;
    case 'state':
      renderState(ev.state);
      break;
    case 'gesture':
      classroom.gesture(ev.kind);
      break;
    case 'lesson_end':
      toast(`Ders bitti: ${ev.topic}`, 'end');
      addLog('note', `Ders özeti: ${ev.summary}`);
      break;
    case 'error':
      toast(ev.message, 'err');
      addLog('note', 'Hata: ' + ev.message);
      break;
    case 'turn_end':
      $('dots').hidden = true;
      break;
  }
}

// ---------------------------------------------------------------- karne ve kelime duvarı
function renderState(s) {
  $('student-name').textContent = s.profile.name || 'Yeni öğrenci';
  $('cefr').textContent = s.profile.level || '?';
  $('xp-level').textContent = s.xp_level;
  $('xp-text').textContent = `${s.xp_in_level} / ${s.xp_per_level} XP`;
  $('xp-bar').style.width = `${(s.xp_in_level / s.xp_per_level) * 100}%`;
  const skills = $('skills');
  if (!skills.children.length) {
    for (const key of Object.keys(SKILL_LABELS)) {
      skills.insertAdjacentHTML('beforeend',
        `<div class="skill"><span>${SKILL_LABELS[key]}</span><div class="bar"><div class="bar-fill" data-skill="${key}"></div></div><b data-val="${key}">0</b></div>`);
    }
  }
  for (const [key, value] of Object.entries(s.skills)) {
    const bar = skills.querySelector(`[data-skill="${key}"]`);
    if (bar) bar.style.width = `${value}%`;
    const val = skills.querySelector(`[data-val="${key}"]`);
    if (val) val.textContent = value;
  }
  $('word-count').textContent = `${s.vocab_total} kelime`;
  $('due-count').textContent = s.due_count ? `${s.due_count} tekrar bekliyor` : '';
  classroom?.setWords(s.vocab);
}

// ---------------------------------------------------------------- konuşma balonu
function showBubble() {
  $('bubble').hidden = false;
}

function placeBubble() {
  if (classroom && !$('bubble').hidden) {
    const p = classroom.teacherHeadOnScreen();
    const b = $('bubble');
    const w = b.offsetWidth, h = b.offsetHeight;
    const x = Math.max(16 + w * 0.82, Math.min(window.innerWidth - 16 - w * 0.18, p.x));
    const y = Math.max(h + 76, Math.min(window.innerHeight - 160, p.y));
    b.style.left = `${x}px`;
    b.style.top = `${y}px`;
  }
  requestAnimationFrame(placeBubble);
}

// ---------------------------------------------------------------- soru kartı
function showQuestion(q) {
  activeQuestion = q;
  $('q-kind').textContent = KIND_LABELS[q.kind] || 'Soru';
  const prompt = $('q-prompt');
  prompt.textContent = '';
  q.prompt.split(/(__+)/).forEach((part) => {
    if (/^__+$/.test(part)) {
      const blank = document.createElement('span');
      blank.className = 'blank';
      prompt.appendChild(blank);
    } else {
      prompt.appendChild(document.createTextNode(part));
    }
  });
  $('q-hint').textContent = q.hint_tr ? `İpucu: ${q.hint_tr}` : '';
  const opts = $('q-options');
  opts.textContent = '';
  for (const o of q.options || []) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'opt';
    b.textContent = o;
    b.onclick = () => send(o, 'answer');
    opts.appendChild(b);
  }
  if (q.kind === 'speak' && mic.supported) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'opt big-mic';
    b.textContent = '🎤 Bas ve konuş';
    b.onclick = () => { voice.stop(); mic.toggle(); };
    opts.appendChild(b);
  }
  $('question').hidden = false;
  if (q.kind !== 'multiple_choice') $('input').focus();
  addLog('note', `Soru kartı: ${q.prompt}`);
}

function hideQuestion() {
  activeQuestion = null;
  $('question').hidden = true;
}

// ---------------------------------------------------------------- kırmızı kalem
function showCorrection(c) {
  $('corr-original').textContent = c.original;
  $('corr-fixed').textContent = c.corrected;
  $('corr-why').textContent = c.explanation_tr;
  const el = $('correction');
  el.hidden = true;
  void el.offsetWidth; // animasyonu yeniden başlat
  el.hidden = false;
  clearTimeout(correctionTimer);
  correctionTimer = setTimeout(() => (el.hidden = true), 12000);
}

// ---------------------------------------------------------------- defter
function addLog(kind, text) {
  const item = document.createElement('div');
  item.className = `log-item ${kind}`;
  if (kind === 'teacher' || kind === 'student') {
    const who = document.createElement('div');
    who.className = 'who';
    who.textContent = kind === 'teacher' ? 'Ms. Clara' : 'Sen';
    item.appendChild(who);
  }
  const body = document.createElement('div');
  body.className = 'text';
  body.textContent = text;
  item.appendChild(body);
  $('log-list').appendChild(item);
  scrollLog();
  return item;
}

function addFixLog(c) {
  const item = document.createElement('div');
  item.className = 'log-item fix';
  const s = document.createElement('s');
  s.textContent = c.original;
  const span = document.createElement('span');
  span.textContent = c.corrected;
  const why = document.createElement('div');
  why.textContent = c.explanation_tr;
  item.append(s, document.createElement('br'), span, why);
  $('log-list').appendChild(item);
  scrollLog();
}

function scrollLog() {
  const list = $('log-list');
  list.scrollTop = list.scrollHeight;
}

function toast(text, kind = '') {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = text;
  $('toasts').appendChild(el);
  setTimeout(() => el.remove(), kind === 'err' ? 8000 : kind === 'end' ? 10000 : 4200);
}

// ---------------------------------------------------------------- yazma kutusu
function autoGrow() {
  const t = $('input');
  t.style.height = 'auto';
  t.style.height = `${Math.min(120, t.scrollHeight)}px`;
  t.style.overflowY = t.scrollHeight > 120 ? 'auto' : 'hidden';
}

$('composer').addEventListener('submit', (e) => {
  e.preventDefault();
  send($('input').value);
  $('input').value = '';
  autoGrow();
});
$('input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $('composer').requestSubmit();
  }
});
$('input').addEventListener('input', autoGrow);
$('mic-btn').addEventListener('click', () => { voice.stop(); mic.toggle(); });
$('sound-btn').addEventListener('click', () => {
  voice.setEnabled(!voice.enabled);
  $('sound-btn').classList.toggle('off', !voice.enabled);
  $('sound-wave').style.display = voice.enabled ? '' : 'none';
  $('sound-btn').title = voice.enabled ? 'Öğretmenin sesi açık' : 'Öğretmenin sesi kapalı';
});
$('log-btn').addEventListener('click', () => {
  $('log').hidden = !$('log').hidden;
  scrollLog();
});
$('log-close').addEventListener('click', () => ($('log').hidden = true));

// ---------------------------------------------------------------- başlat
classroom = new Classroom($('stage'));
document.fonts?.load('72px "Patrick Hand"').then(() => {
  classroom.wordWall.draw();
  classroom.notebook.draw();
  classroom.board.draw();
});
requestAnimationFrame(placeBubble);

$('enter-btn').addEventListener('click', () => {
  voice.unlock();
  $('splash').hidden = true;
  connect();
  $('input').focus();
});
