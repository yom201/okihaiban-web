(() => {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const canObserve = 'IntersectionObserver' in window;

  // スクロールで現れる（台本が動かない時は最初から見えたまま）
  if (canObserve && !reduceMotion) {
    const targets = document.querySelectorAll(
      'main > section.section-band .section-heading, .setup-steps > li, .record-grid > article, .feature-summary-grid > article, .screens-stage, .screen-thumbs'
    );
    let alive = false;
    const io = new IntersectionObserver((entries) => {
      alive = true;
      entries.forEach((e) => {
        if (e.isIntersecting) {
          e.target.classList.add('is-in');
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.12 });
    targets.forEach((el) => {
      el.classList.add('reveal');
      io.observe(el);
    });
    // 監視が一度も動かない環境では、中身を隠したままにしない
    setTimeout(() => {
      if (!alive) targets.forEach((el) => el.classList.add('is-in'));
    }, 3000);
  }

  // 検知の流れ：画面に入ったら 1→2→3 の順に光る
  const flow = document.querySelector('.detect-flow');
  if (flow) {
    const steps = [...flow.querySelectorAll('li')];
    let timer = null;
    const run = () => {
      if (reduceMotion) {
        steps.forEach((s) => s.classList.add('is-lit'));
        return;
      }
      let i = 0;
      clearInterval(timer);
      timer = setInterval(() => {
        steps.forEach((s, n) => s.classList.toggle('is-lit', n === i % (steps.length + 1)));
        i += 1;
      }, 1100);
    };
    const stop = () => { clearInterval(timer); timer = null; };
    if (canObserve) {
      new IntersectionObserver((entries) => {
        entries.forEach((e) => (e.isIntersecting ? run() : stop()));
      }, { threshold: 0.4 }).observe(flow);
    } else {
      steps.forEach((s) => s.classList.add('is-lit'));
    }
  }

  // 設定画面：端末の枠で自動切替＋タップの印
  const stage = document.querySelector('[data-screens]');
  if (!stage) return;
  const shots = [...stage.querySelectorAll('.phone-shot')];
  const captions = [...stage.querySelectorAll('.screen-caption')];
  const thumbs = [...document.querySelectorAll('.screen-thumb')];
  const ring = stage.querySelector('.tap-ring');
  const frame = stage.querySelector('.phone-frame');
  let index = 0;
  let timers = [];
  let visible = false;

  const clearTimers = () => { timers.forEach(clearTimeout); timers = []; };
  const taps = (el) => (el.dataset.taps || '').split(';').filter(Boolean).map((p) => p.split(',').map(Number));

  const show = (next) => {
    index = (next + shots.length) % shots.length;
    shots.forEach((s, n) => s.classList.toggle('is-active', n === index));
    captions.forEach((c, n) => c.classList.toggle('is-active', n === index));
    thumbs.forEach((t, n) => t.classList.toggle('is-active', n === index));
  };

  const tapAt = ([x, y]) => {
    const shot = shots[index];
    const top = shot.offsetTop;
    ring.style.left = `${x}%`;
    ring.style.top = `${top + (shot.offsetHeight * y) / 100}px`;
    ring.classList.remove('is-tapping');
    void ring.offsetWidth;
    ring.classList.add('is-tapping');
  };

  const cycle = () => {
    clearTimers();
    if (!visible || reduceMotion) return;
    const points = taps(shots[index]);
    points.forEach((p, n) => timers.push(setTimeout(() => tapAt(p), 900 + n * 1200)));
    timers.push(setTimeout(() => { show(index + 1); cycle(); }, 1400 + points.length * 1200));
  };

  frame.addEventListener('click', () => { show(index + 1); cycle(); });
  thumbs.forEach((t) => t.addEventListener('click', () => { show(Number(t.dataset.index)); cycle(); }));

  if (canObserve) {
    new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        visible = e.isIntersecting;
        if (visible) cycle(); else clearTimers();
      });
    }, { threshold: 0.35 }).observe(frame);
  }
})();
