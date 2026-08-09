<script setup lang="ts">
import { ref } from "vue";

import financialJournalHero from "@/assets/auth/financial-journal-hero-cutout.webp";
import BrandMark from "@/components/BrandMark.vue";
import { usePointerParallax } from "@/composables/usePointerParallax";

const hero = ref<HTMLElement | null>(null);
usePointerParallax(hero);
</script>

<template>
  <section ref="hero" class="welcome-hero" aria-labelledby="welcome-title">
    <div class="paper-grain" aria-hidden="true" />
    <header class="welcome-brand"><BrandMark /></header>

    <div class="welcome-copy">
      <p class="welcome-kicker">PERSONAL FINANCIAL INTELLIGENCE</p>
      <h1 id="welcome-title">
        <span>让财富，</span>
        <span>更清晰。</span>
      </h1>
      <span class="brush-underline" aria-hidden="true" />
      <p class="welcome-description">
        把分散的账户、交易与想法，<br />
        整理成属于你的财务脉络。
      </p>
    </div>

    <figure class="welcome-visual">
      <div class="hero-artwork-shell">
        <img
          :src="financialJournalHero"
          alt="打开的财务笔记本、账户纸片、铅笔、指南针与橙色太阳构成的手绘财务场景"
          width="1254"
          height="1254"
        />
        <svg
          class="hero-orbit-overlay"
          viewBox="0 0 100 100"
          aria-hidden="true"
        >
          <path d="M57 19C68 1 94 1 98 16c5 18-14 27-33 20-13-5-17-13-8-17Z" />
          <circle cx="0" cy="0" r="0.8" />
        </svg>
      </div>
    </figure>

    <a class="explore-cue" href="#login-access" aria-label="向下探索登录区域">
      <span class="mouse-outline" aria-hidden="true"><i /></span>
      <span>向下探索</span>
      <svg viewBox="0 0 24 28" aria-hidden="true">
        <path d="M12 2v21m-7-7 7 7 7-7" />
      </svg>
    </a>
  </section>
</template>

<style scoped>
.welcome-hero {
  --pointer-x: 0;
  --pointer-y: 0;
  position: relative;
  display: grid;
  min-height: 100svh;
  padding: clamp(26px, 4.2vw, 68px) clamp(32px, 7vw, 128px) 110px;
  grid-template-columns: minmax(370px, 0.9fr) minmax(500px, 1.1fr);
  grid-template-rows: auto 1fr;
  column-gap: clamp(18px, 3vw, 60px);
  color: var(--graphite-900);
  background:
    linear-gradient(104deg, rgb(255 247 224 / 44%), transparent 42%),
    linear-gradient(165deg, var(--canvas-light), var(--canvas));
  isolation: isolate;
  overflow: hidden;
}

.paper-grain {
  position: absolute;
  z-index: -1;
  inset: 0;
  background:
    linear-gradient(rgb(255 248 226 / 13%), rgb(201 160 91 / 9%)),
    url("../../assets/auth/ochre-canvas-texture.webp") center / 768px repeat;
  mix-blend-mode: multiply;
  opacity: 0.46;
  pointer-events: none;
}

.welcome-brand {
  z-index: 2;
  grid-column: 1 / -1;
  animation: logo-arrive 700ms 100ms both ease-out;
}

.welcome-copy {
  z-index: 2;
  align-self: center;
  justify-self: center;
  width: min(100%, 560px);
  padding: 4vh 0 7vh;
  transform: translateX(clamp(12px, 2.4vw, 42px));
}

.welcome-kicker {
  margin: 0 0 clamp(22px, 4vh, 40px);
  color: var(--orange-600);
  font-size: clamp(10px, 0.8vw, 12px);
  font-weight: 750;
  letter-spacing: 0.19em;
}

.welcome-copy h1 {
  margin: 0;
  font-family: "Iowan Old Style", "Songti SC", "STSong", serif;
  font-size: clamp(58px, 7.1vw, 112px);
  font-weight: 620;
  letter-spacing: -0.065em;
  line-height: 1.02;
}

.welcome-copy h1 span {
  display: block;
  animation: title-arrive 820ms both cubic-bezier(0.22, 1, 0.36, 1);
}

.welcome-copy h1 span:first-child {
  animation-delay: 240ms;
}

.welcome-copy h1 span:last-child {
  animation-delay: 380ms;
}

.brush-underline {
  display: block;
  width: clamp(120px, 13vw, 210px);
  height: 13px;
  margin: 20px 0 28px 3px;
  background:
    linear-gradient(
      177deg,
      transparent 31%,
      var(--orange-400) 35% 66%,
      transparent 71%
    ),
    linear-gradient(
      2deg,
      transparent 42%,
      rgb(201 111 69 / 55%) 45% 62%,
      transparent 65%
    );
  clip-path: polygon(
    0 34%,
    8% 25%,
    24% 36%,
    42% 22%,
    65% 30%,
    83% 18%,
    100% 31%,
    98% 70%,
    76% 66%,
    54% 76%,
    31% 66%,
    8% 78%,
    0 65%
  );
  transform: scaleX(0);
  transform-origin: left center;
  animation: brush-in 760ms 780ms forwards cubic-bezier(0.2, 0.8, 0.2, 1);
}

.welcome-description {
  margin: 0;
  color: var(--graphite-700);
  font-size: clamp(15px, 1.3vw, 20px);
  letter-spacing: 0.02em;
  line-height: 1.9;
  animation: logo-arrive 700ms 800ms both ease-out;
}

.welcome-visual {
  align-self: center;
  width: min(100%, 820px);
  height: min(72svh, 720px);
  margin: 0;
  justify-self: center;
  transform: translate(1%, 2%) scale(1.1);
}

.hero-artwork-shell {
  position: relative;
  height: 100%;
  transform: translate(
    calc(var(--pointer-x) * 4px),
    calc(var(--pointer-y) * 4px)
  );
  transition: transform 220ms ease-out;
}

.hero-artwork-shell img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  opacity: 0;
  filter: saturate(0.9) contrast(0.94) sepia(0.04);
  animation: artwork-arrive 1100ms 420ms forwards cubic-bezier(0.22, 1, 0.36, 1);
}

.hero-orbit-overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
}

.hero-orbit-overlay path {
  fill: none;
  stroke: var(--orange-600);
  stroke-dasharray: 1.2 1.1;
  stroke-dashoffset: 80;
  stroke-linecap: round;
  stroke-width: 0.16;
  opacity: 0.52;
  animation: orbit-draw 1800ms 1000ms forwards ease-out;
}

.hero-orbit-overlay circle {
  fill: var(--orange-600);
  offset-path: path("M57 19C68 1 94 1 98 16c5 18-14 27-33 20-13-5-17-13-8-17Z");
  animation: orbit-travel 15s 1.8s infinite linear;
}

.explore-cue {
  position: absolute;
  z-index: 4;
  bottom: clamp(18px, 3vh, 34px);
  left: 50%;
  display: grid;
  color: var(--graphite-700);
  font-size: 11px;
  letter-spacing: 0.12em;
  place-items: center;
  text-decoration: none;
  transform: translateX(-50%);
}

.mouse-outline {
  position: relative;
  width: 25px;
  height: 38px;
  margin-bottom: 7px;
  border: 1.6px solid currentColor;
  border-radius: 48% 52% 45% 55% / 44% 48% 52% 56%;
  transform: rotate(-2deg);
}

.mouse-outline i {
  position: absolute;
  top: 7px;
  left: 50%;
  width: 2px;
  height: 7px;
  border-radius: 2px;
  background: var(--orange-600);
  transform: translateX(-50%);
}

.explore-cue svg {
  width: 17px;
  margin-top: 4px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.4;
  animation: arrow-breathe 2.6s 1.8s infinite ease-in-out;
}

@keyframes logo-arrive {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes title-arrive {
  from {
    opacity: 0;
    transform: translateY(22px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes brush-in {
  to {
    transform: scaleX(1);
  }
}

@keyframes artwork-arrive {
  from {
    opacity: 0;
    transform: translateY(16px) scale(0.97);
  }
  to {
    opacity: 0.98;
    transform: translateY(0) scale(1);
  }
}

@keyframes orbit-draw {
  to {
    stroke-dashoffset: 0;
  }
}

@keyframes orbit-travel {
  to {
    offset-distance: 100%;
  }
}

@keyframes arrow-breathe {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(4px);
  }
}

@media (max-width: 900px) {
  .welcome-hero {
    min-height: 100svh;
    padding: 24px clamp(20px, 6vw, 54px) 90px;
    grid-template-columns: 1fr;
    grid-template-rows: auto auto minmax(260px, 1fr);
  }

  .welcome-copy {
    padding: clamp(32px, 6vh, 62px) 0 8px;
    transform: none;
  }

  .welcome-copy h1 {
    font-size: clamp(54px, 12vw, 88px);
  }

  .welcome-kicker {
    margin-bottom: 20px;
  }

  .brush-underline {
    margin-block: 13px 16px;
  }

  .welcome-visual {
    width: min(90%, 620px);
    height: min(42svh, 420px);
    margin-top: -10px;
    transform: none;
  }
}

@media (max-width: 600px) {
  .welcome-hero {
    padding-inline: 20px;
  }

  .welcome-copy {
    padding-top: 34px;
  }

  .welcome-copy h1 {
    font-size: clamp(48px, 17vw, 76px);
  }

  .welcome-description {
    font-size: 14px;
    line-height: 1.75;
  }

  .welcome-visual {
    width: 115%;
    height: min(38svh, 340px);
    margin-top: -2px;
    transform: translateX(3%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .welcome-brand,
  .welcome-copy h1 span,
  .welcome-description,
  .explore-cue svg {
    animation: none;
  }

  .brush-underline {
    animation: none;
    transform: none;
  }

  .hero-artwork-shell {
    transform: none;
    transition: none;
  }

  .hero-artwork-shell img {
    opacity: 0.98;
    animation: none;
  }

  .hero-orbit-overlay path {
    stroke-dashoffset: 0;
    animation: none;
  }

  .hero-orbit-overlay circle {
    animation: none;
  }
}
</style>
