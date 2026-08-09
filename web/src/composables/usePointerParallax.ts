import { onBeforeUnmount, onMounted, type Ref } from "vue";

export function usePointerParallax(target: Ref<HTMLElement | null>): void {
  let frame = 0;
  let canMove = false;
  let pointerQuery: MediaQueryList | undefined;
  let motionQuery: MediaQueryList | undefined;

  const reset = (): void => {
    if (!target.value) return;
    target.value.style.setProperty("--pointer-x", "0");
    target.value.style.setProperty("--pointer-y", "0");
  };

  const updateCapability = (): void => {
    canMove = Boolean(pointerQuery?.matches && !motionQuery?.matches);
    if (!canMove) reset();
  };

  const handlePointerMove = (event: PointerEvent): void => {
    if (!canMove || !target.value) return;
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      const x = (event.clientX / window.innerWidth - 0.5) * 2;
      const y = (event.clientY / window.innerHeight - 0.5) * 2;
      target.value?.style.setProperty("--pointer-x", x.toFixed(3));
      target.value?.style.setProperty("--pointer-y", y.toFixed(3));
    });
  };

  onMounted(() => {
    if (!window.matchMedia) return;
    pointerQuery = window.matchMedia(
      "(pointer: fine) and (min-width: 601px)",
    );
    motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    updateCapability();
    window.addEventListener("pointermove", handlePointerMove, {
      passive: true,
    });
    pointerQuery.addEventListener("change", updateCapability);
    motionQuery.addEventListener("change", updateCapability);
  });

  onBeforeUnmount(() => {
    cancelAnimationFrame(frame);
    window.removeEventListener("pointermove", handlePointerMove);
    pointerQuery?.removeEventListener("change", updateCapability);
    motionQuery?.removeEventListener("change", updateCapability);
  });
}
