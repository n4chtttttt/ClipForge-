const $ = (id) => document.getElementById(id);
const state = {upload: null, jobs: [], selectedJob: null, selectedClip: 0, poller: null, busy: false};

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
  for (const job of state.jobs) {
    const button = document.createElement('button');
    button.className = `job-tab${job.id === state.selectedJob ? ' active' : ''}`;
    button.type = 'button';
    const title = document.createElement('div');
    title.className = 'tab-top';
    const name = document.createElement('span');
    name.className = 'tab-title';
    name.textContent = (job.source || 'Video job').split(/[\\/]/).pop();
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
  $('download-link').href = `${url}?download=1`;
  $('download-link').download = `clipforge_${job.id}_clip_${String(index + 1).padStart(2, '0')}.mp4`;
  for (const row of $('clip-list').querySelectorAll('.clip-row')) row.classList.toggle('active', Number(row.dataset.index) === index);
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
    empty.textContent = 'No moments met the current scoring criteria. Try a longer source or wider clip duration.';
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
  $('review-title').textContent = (job.source || 'Video job').split(/[\\/]/).pop();
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
    else state.selectedJob = state.jobs[0]?.id || null;
    renderJobs();
    renderSelectedJob();
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
      options: {top_n: Number($('clip-count').value), min_clip_seconds: Number($('min-duration').value), max_clip_seconds: Number($('max-duration').value), whisper_model: $('model').value, whisper_device: $('device').value}
    })});
    state.selectedJob = data.job_id;
    state.selectedClip = 0;
    await loadJobs();
  } catch (error) { showError(error.message); }
  finally { state.busy = false; $('start-button').querySelector('span').textContent = 'Find moments'; $('start-button').disabled = !state.upload; }
}

$('video-file').addEventListener('change', event => uploadFile(event.target.files[0]));
$('start-button').addEventListener('click', startJob);
$('refresh-button').addEventListener('click', loadJobs);
$('logs-toggle').addEventListener('click', () => {
  const logs = $('job-logs');
  logs.hidden = !logs.hidden;
  $('logs-toggle').setAttribute('aria-expanded', String(!logs.hidden));
  $('logs-toggle').textContent = logs.hidden ? 'Show log' : 'Hide log';
});
for (const input of [$('min-duration'), $('max-duration')]) input.addEventListener('input', () => $('duration-value').textContent = `${$('min-duration').value}–${$('max-duration').value} sec`);
const drop = $('dropzone');
for (const event of ['dragenter', 'dragover']) drop.addEventListener(event, e => { e.preventDefault(); drop.classList.add('dragging'); });
for (const event of ['dragleave', 'drop']) drop.addEventListener(event, e => { e.preventDefault(); drop.classList.remove('dragging'); });
drop.addEventListener('drop', event => uploadFile(event.dataTransfer.files[0]));
loadJobs();
