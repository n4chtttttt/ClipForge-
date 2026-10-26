const $ = (id) => document.getElementById(id);
const state = {upload: null, jobs: [], selectedJob: null, selectedClip: 0, poller: null, busy: false,
  view: 'desk', sessionJobs: new Set()};

function displayName(job) {
  // Upload files are stored as "<32 hex id>_<name>"; hide the id from the UI.
  return (job.source || 'Video job').split(/[\\/]/).pop().replace(/^[a-f0-9]{32}_/, '');
}

function setView(view) {
  state.view = view;
  $('desk-view').hidden = view !== 'desk';
  $('library-view').hidden = view !== 'library';
  for (const [id, name] of [['tab-desk', 'desk'], ['tab-library', 'library']]) {
    $(id).classList.toggle('active', view === name);
    $(id).setAttribute('aria-selected', String(view === name));
  }
}

function showError(message) {
  const box = $('error-banner');
  box.textContent = message;
  box.hidden = !message;
}

function durationLabel(seconds) {
  const whole = Math.max(0, Math.round(seconds || 0));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

function timeLabel(seconds) {
  return durationLabel(seconds);
}

function titleFor(moment, index) {
  return (moment.title || `Moment ${String(index + 1).padStart(2, '0')}`).replace(/\s+/g, ' ').trim();
}

async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

async function uploadFile(file) {
  showError('');
  if (!file) return;
  const allowed = /\.(mp4|mov|mkv|avi|webm|m4v)$/i.test(file.name);
  if (!allowed) { showError('Use an MP4, MOV, MKV, AVI, WebM, or M4V video.'); return; }
  state.busy = true;
  $('start-button').disabled = true;
  $('file-name').textContent = file.name;
  $('file-hint').textContent = 'Uploading video…';
  $('dropzone').classList.remove('dragging');
  try {
    const result = await request('/api/upload', {
      method: 'POST',
      headers: {'Content-Type': 'application/octet-stream', 'X-File-Name': encodeURIComponent(file.name)},
      body: file
    });
    state.upload = result;
    $('file-name').textContent = result.filename;
    $('file-hint').textContent = `${(result.bytes / 1024 / 1024).toFixed(1)} MB · ready to process`;
    $('start-button').disabled = false;
  } catch (error) {
    state.upload = null;
    $('file-name').textContent = 'Drop a video here';
    $('file-hint').textContent = 'or browse files';
    showError(error.message);
  } finally {
    state.busy = false;
  }
}

function renderJobs() {
  const strip = $('job-strip');
  strip.replaceChildren();
  const visible = state.jobs.filter(job => state.sessionJobs.has(job.id) || ['running', 'queued'].includes(job.status));
  strip.hidden = visible.length === 0;
  for (const job of visible) {
    const button = document.createElement('button');
    button.className = `job-tab${job.id === state.selectedJob ? ' active' : ''}`;
    button.type = 'button';
    const title = document.createElement('div');
    title.className = 'tab-top';
    const name = document.createElement('span');
    name.className = 'tab-title';
    name.textContent = displayName(job)
    title.append(name);
    const status = document.createElement('div');
    status.className = `tab-state ${job.status}`;
    status.textContent = job.status === 'running' ? `${job.progress || 0}% · ${job.stage}` : job.status;
    button.append(title, status);
    button.addEventListener('click', () => selectJob(job.id));
    strip.append(button);
  }
}

function renderLog(job) {
  $('job-logs').textContent = (job.logs || []).map(item => {
    const time = new Date(item.time * 1000).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'});
    return `${time}  ${item.message}`;
  }).join('\n');
}

function clipUrl(job, index) {
  const clip = `clip_${String(index + 1).padStart(2, '0')}.mp4`;
  return `/media/${job.id}/${clip}`;
}

function selectClip(index) {
  const job = state.jobs.find(item => item.id === state.selectedJob);
  if (!job?.result?.moments?.[index]) return;
  state.selectedClip = index;
  const moment = job.result.moments[index];
  const url = clipUrl(job, index);
  const player = $('clip-player');
  player.src = url;
  $('player-empty').hidden = true;
  $('clip-title').textContent = titleFor(moment, index);
  $('clip-range').textContent = `${timeLabel(moment.start)} — ${timeLabel(moment.end)}`;
  $('clip-duration').textContent = `${Math.round(moment.end - moment.start)} sec`;
  $('clip-score').textContent = Number(moment.score).toFixed(1);
  $('clip-reason').textContent = moment.reason || '—';
  const rating = job.feedback?.[String(index)];
  $('feedback-keep').classList.toggle('active', rating === 1);
  $('feedback-reject').classList.toggle('active', rating === -1);
  $('download-link').href = `${url}?download=1`;
  $('download-link').download = `clipforge_${job.id}_clip_${String(index + 1).padStart(2, '0')}.mp4`;
  for (const row of $('clip-list').querySelectorAll('.clip-row')) row.classList.toggle('active', Number(row.dataset.index) === index);
}

async function saveFeedback(rating) {
  const job = state.jobs.find(item => item.id === state.selectedJob);
  if (!job) return;
  try {
    await request(`/api/jobs/${job.id}/feedback`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({clip_index: state.selectedClip, rating})
    });
    job.feedback ||= {};
    job.feedback[String(state.selectedClip)] = rating === 'keep' ? 1 : -1;
    selectClip(state.selectedClip);
  } catch (error) { showError(error.message); }
}

function renderClips(job) {
  const section = $('clips-section');
  const moments = job.result?.moments || [];
  const clips = job.result?.clips || [];
  if (job.status !== 'done') { section.hidden = true; return; }
  section.hidden = false;
  $('clip-total').textContent = String(moments.length);
  const list = $('clip-list');
  list.replaceChildren();
  if (!moments.length) {
    const empty = document.createElement('div');
    empty.className = 'no-clips';
    empty.textContent = 'No moments met the current scoring criteria. Try a longer source or a shorter minimum duration.';
    list.append(empty);
    $('player-empty').hidden = false;
    $('clip-player').removeAttribute('src');
    return;
  }
  moments.forEach((moment, index) => {
    if (!clips[index]) return;
    const row = document.createElement('button');
    row.type = 'button';
    row.dataset.index = String(index);
    row.className = `clip-row${index === state.selectedClip ? ' active' : ''}`;
    const number = document.createElement('span'); number.className = 'clip-index'; number.textContent = String(index + 1).padStart(2, '0');
    const title = document.createElement('span'); title.className = 'clip-name'; title.textContent = titleFor(moment, index);
    const time = document.createElement('span'); time.className = 'clip-time'; time.textContent = `${timeLabel(moment.start)}–${timeLabel(moment.end)}`;
    const reason = document.createElement('span'); reason.className = 'clip-reason'; reason.textContent = moment.reason || '—';
    const score = document.createElement('span'); score.className = 'clip-score'; score.textContent = Number(moment.score).toFixed(1);
    const open = document.createElement('span'); open.className = 'clip-open'; open.textContent = '›';
    row.append(number, title, time, reason, score, open);
    row.addEventListener('click', () => selectClip(index));
    list.append(row);
  });
  if (!job.result.moments[state.selectedClip]) state.selectedClip = 0;
  selectClip(state.selectedClip);
}

function renderLibrary() {
  $('library-count').textContent = String(state.jobs.length);
  const list = $('library-list');
  list.replaceChildren();
  if (!state.jobs.length) {
    const empty = document.createElement('div');
    empty.className = 'library-empty';
    empty.textContent = 'Nothing saved yet. Clips you make will show up here.';
    list.append(empty);
    return;
  }
  for (const job of state.jobs) {
    const card = document.createElement('div');
    card.className = 'library-card';
    const info = document.createElement('div');
    const name = document.createElement('div');
    name.className = 'library-name';
    name.textContent = displayName(job);
    name.title = displayName(job);
    const meta = document.createElement('div');
    meta.className = 'library-meta';
    const status = document.createElement('span');
    status.className = job.status;
    status.textContent = job.status;
    const count = job.result?.clips?.length;
    const when = new Date(job.created * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'});
    meta.append(status, ` · ${count != null ? `${count} clips · ` : ''}${when}`);
    info.append(name, meta);
    const open = document.createElement('button');
    open.type = 'button'; open.className = 'library-open'; open.textContent = 'Open';
    open.addEventListener('click', () => openFromLibrary(job.id));
    const del = document.createElement('button');
    del.type = 'button'; del.className = 'library-delete'; del.textContent = 'Delete';
    del.addEventListener('click', () => deleteJob(job));
    card.append(info, open, del);
    list.append(card);
  }
}

function openFromLibrary(id) {
  state.sessionJobs.add(id);
  setView('desk');
  selectJob(id);
}

async function deleteJob(job) {
  if (!confirm(`Delete "${displayName(job)}" and its clips from this computer? This can't be undone.`)) return;
  try {
    await request(`/api/jobs/${job.id}`, {method: 'DELETE'});
    state.sessionJobs.delete(job.id);
    if (state.selectedJob === job.id) state.selectedJob = null;
    await loadJobs();
  } catch (error) { showError(error.message); }
}

function renderSelectedJob() {
  const job = state.jobs.find(item => item.id === state.selectedJob);
  if (!job) {
    $('empty-state').hidden = false;
    $('job-view').hidden = true;
    $('review-title').textContent = 'Your cuts, in one place';
    return;
  }
  $('empty-state').hidden = true;
  $('job-view').hidden = false;
  $('review-title').textContent = displayName(job);
  $('job-source').textContent = job.source || '';
  $('progress-panel').hidden = job.status === 'done';
  if (job.status !== 'done') {
    $('job-stage').textContent = job.stage || (job.status === 'queued' ? 'Queued' : 'Working');
    $('job-percent').textContent = `${job.progress || 0}%`;
    $('progress-fill').style.width = `${Math.min(100, job.progress || 0)}%`;
    $('job-failure').hidden = job.status !== 'failed';
    $('job-failure').textContent = job.status === 'failed' ? (job.error || 'The job failed. Check the log for details.') : '';
    renderLog(job);
  }
  renderClips(job);
}

async function loadJobs() {
  try {
    const data = await request('/api/jobs');
    const previous = state.selectedJob;
    state.jobs = data.jobs || [];
    if (previous && state.jobs.some(job => job.id === previous)) state.selectedJob = previous;
    else {
      state.selectedJob = state.jobs.find(job => ['running', 'queued'].includes(job.status))?.id || null;
      if (state.selectedJob) state.sessionJobs.add(state.selectedJob);
    }
    renderJobs();
    renderSelectedJob();
    renderLibrary();
    const active = state.jobs.some(job => ['running', 'queued'].includes(job.status));
    if (active && !state.poller) state.poller = setInterval(loadJobs, 1400);
    if (!active && state.poller) { clearInterval(state.poller); state.poller = null; }
  } catch (error) { showError(`Could not load jobs: ${error.message}`); }
}

async function selectJob(id) {
  state.selectedJob = id;
  state.selectedClip = 0;
  renderJobs();
  renderSelectedJob();
}

async function startJob() {
  if (!state.upload || state.busy) return;
  showError('');
  state.busy = true;
  $('start-button').disabled = true;
  $('start-button').querySelector('span').textContent = 'Starting…';
  try {
    const data = await request('/api/jobs', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
      upload_id: state.upload.upload_id,
      options: {top_n: Number($('clip-count').value), min_clip_seconds: Number($('min-duration').value), whisper_model: $('model').value, whisper_device: $('device').value, whisper_language: $('language').value, scorer_mode: $('scorer-mode').value, ranker_model: 'qwen2.5vl:3b'}
    })});
    state.selectedJob = data.job_id;
    state.sessionJobs.add(data.job_id);
    state.selectedClip = 0;
    setView('desk');
    await loadJobs();
  } catch (error) { showError(error.message); }
  finally { state.busy = false; $('start-button').querySelector('span').textContent = 'Find moments'; $('start-button').disabled = !state.upload; }
}

$('video-file').addEventListener('change', event => uploadFile(event.target.files[0]));
$('start-button').addEventListener('click', startJob);
$('feedback-keep').addEventListener('click', () => saveFeedback('keep'));
$('feedback-reject').addEventListener('click', () => saveFeedback('reject'));
$('refresh-button').addEventListener('click', loadJobs);
$('tab-desk').addEventListener('click', () => setView('desk'));
$('tab-library').addEventListener('click', () => { setView('library'); loadJobs(); });
$('logs-toggle').addEventListener('click', () => {
  const logs = $('job-logs');
  logs.hidden = !logs.hidden;
  $('logs-toggle').setAttribute('aria-expanded', String(!logs.hidden));
  $('logs-toggle').textContent = logs.hidden ? 'Show log' : 'Hide log';
});
function updateDurationLabel() {
  const minimum = Number($('min-duration').value) || 20;
  const maximum = Math.min(minimum * 1.6, 90);
  $('duration-value').textContent = `${minimum} sec min · up to ${Math.round(maximum)} sec max`;
}
$('min-duration').addEventListener('input', updateDurationLabel);
const drop = $('dropzone');
for (const event of ['dragenter', 'dragover']) drop.addEventListener(event, e => { e.preventDefault(); drop.classList.add('dragging'); });
for (const event of ['dragleave', 'drop']) drop.addEventListener(event, e => { e.preventDefault(); drop.classList.remove('dragging'); });
drop.addEventListener('drop', event => uploadFile(event.dataTransfer.files[0]));
loadJobs();
