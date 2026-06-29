(function () {
  'use strict';

  const synth = window.speechSynthesis;
  const muted = new URLSearchParams(window.location.search).get('mute_tts') === '1';

  let enabled = false;
  let desiredVoiceName = '';
  let engine = 'browser';
  let neuralVoice = '';
  let fallbackToBrowser = false;

  let voices = [];
  const queue = [];
  let _speaking = false;

  const pendingNeural = [];
  let _neuralPlaying = false;

  const MAX_QUEUE = 3;
  const MAX_TEXT  = 200;

  function loadVoices() {
    if (!synth) return;
    try {
      const v = synth.getVoices();
      if (v && v.length) voices = Array.from(v);
    } catch (_) {}
  }

  if (synth) {
    try { synth.addEventListener('voiceschanged', loadVoices); } catch (_) {}
    loadVoices();
  }

  function findRuVoice() {
    if (!voices.length) return null;
    if (desiredVoiceName) {
      const match = voices.find(v => v.name === desiredVoiceName && v.lang.startsWith('ru'));
      if (match) return match;
    }
    return voices.find(v => v.lang.startsWith('ru')) || null;
  }

  function drain() {
    if (!synth) return;
    if (_speaking || !queue.length) return;
    const text = queue.shift();
    try {
      const utt = new SpeechSynthesisUtterance(text);
      utt.lang = 'ru-RU';
      const voice = findRuVoice();
      if (voice) utt.voice = voice;
      utt.rate = 1.0;
      utt.onend  = () => { _speaking = false; drain(); };
      utt.onerror = () => { _speaking = false; drain(); };
      _speaking = true;
      synth.speak(utt);
    } catch (_) {
      _speaking = false;
      if (queue.length) setTimeout(drain, 50);
    }
  }

  function browserSpeak(text) {
    if (!synth) return;
    if (queue.length >= MAX_QUEUE) queue.shift();
    queue.push(text);
    drain();
  }

  function drainNeural() {
    if (_neuralPlaying || !pendingNeural.length) return;
    _neuralPlaying = true;
    const text = pendingNeural.shift();
    try {
      fetch('/api/tts/synthesize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice: neuralVoice }),
      })
        .then(res => {
          if (!res.ok) {
            if (fallbackToBrowser) browserSpeak(text);
            _neuralPlaying = false;
            drainNeural();
            return;
          }
          return res.blob().then(blob => {
            const url = URL.createObjectURL(blob);
            const audio = new Audio(url);
            let done = false;
            function cleanup() {
              if (done) return;
              done = true;
              URL.revokeObjectURL(url);
              _neuralPlaying = false;
              drainNeural();
            }
            audio.onended = cleanup;
            audio.onerror = cleanup;
            audio.play().catch(cleanup);
          });
        })
        .catch(() => {
          if (fallbackToBrowser) browserSpeak(text);
          _neuralPlaying = false;
          drainNeural();
        });
    } catch (_) {
      _neuralPlaying = false;
      drainNeural();
    }
  }

  function speak(rawText) {
    if (!enabled || muted) return;
    try {
      let text = String(rawText == null ? '' : rawText).trim();
      if (!text) return;
      text = text.replace(/https?:\/\/\S+/g, '').trim();
      if (!text) return;
      if (text.length > MAX_TEXT) text = text.slice(0, MAX_TEXT);

      if (engine === 'neural') {
        if (pendingNeural.length >= MAX_QUEUE) pendingNeural.shift();
        pendingNeural.push(text);
        drainNeural();
      } else {
        if (queue.length >= MAX_QUEUE) queue.shift();
        queue.push(text);
        drain();
      }
    } catch (_) {}
  }

  function setEnabled(flag) { enabled = !!flag; }
  function setVoice(name)   { desiredVoiceName = String(name || ''); }

  function init() {
    try {
      if (synth) {
        try { synth.cancel(); } catch (_) {}
      }
      queue.length = 0;
      pendingNeural.length = 0;
      _speaking = false;
      _neuralPlaying = false;

      fetch('/api/settings')
        .then(r => r.ok ? r.json() : {})
        .then(data => {
          if (!data) return;
          enabled           = !!data.tts_enabled;
          desiredVoiceName  = String(data.tts_voice || '');
          engine            = data.tts_engine || 'browser';
          neuralVoice       = String(data.tts_neural_voice || '');
          fallbackToBrowser = !!data.tts_fallback_to_browser;
          loadVoices();
        })
        .catch(() => {});
    } catch (_) {}
  }

  window.ChatTTS = { speak, setEnabled, setVoice, init };
})();
