"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { Button } from "@/components/Button";

type TourStep = {
  title: string;
  text: string;
  /** CSS selector of the element to highlight; null = centered card. */
  selector: string | null;
};

const STEPS: TourStep[] = [
  {
    title: "Добро пожаловать в Rivalens",
    text: "Rivalens следит за сайтами ваших конкурентов: цены, новые разделы, вакансии. Когда что-то меняется — вы получаете готовый вывод на почту.",
    selector: null,
  },
  {
    title: "Добавьте конкурента",
    text: "Введите название и адрес сайта конкурента в форму ниже — например, «Севергрупп, https://severstal-tur.ru». Первый снапшот создастся сразу.",
    selector: 'form input[placeholder="Название конкурента"]',
  },
  {
    title: "Проверьте сейчас",
    text: "После добавления откройте конкурента и нажмите «Проверить сейчас» — Rivalens сразу загрузит страницы и покажет, что изменилось.",
    selector: null,
  },
  {
    title: "Смотрите изменения",
    text: "На странице конкурента — список последних изменений и инсайты: короткие выводы о том, что изменилось и что это значит для вас.",
    selector: null,
  },
  {
    title: "Получайте письма",
    text: "Раз в неделю приходит дайджест: что изменилось у всех конкурентов. Ничего не нужно проверять вручную.",
    selector: null,
  },
];

/** 5-step onboarding overlay with element highlighting (CP27).
 *  Highlight = a bordered rect positioned over the target's
 *  getBoundingClientRect; the rest of the screen dims. Next/Skip per step. */
export function OnboardingTour({
  open,
  onComplete,
  onSkip,
}: {
  open: boolean;
  onComplete: () => void;
  onSkip: () => void;
}) {
  const [step, setStep] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const rectRef = useRef<HTMLDivElement | null>(null);

  const current = STEPS[step];

  // Recompute the highlight on every step and on resize/scroll.
  const selector = current.selector;
  useLayoutEffect(() => {
    if (!open || selector === null) {
      setRect(null);
      return;
    }
    let cancelled = false;
    const update = () => {
      if (cancelled) return;
      const el = document.querySelector(selector);
      if (el === null) {
        setRect(null);
        return;
      }
      setRect(el.getBoundingClientRect());
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      cancelled = true;
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open, selector, step]);

  useEffect(() => {
    if (open) setStep(0);
  }, [open]);

  if (!open) return null;

  const isLast = step === STEPS.length - 1;

  // Card sits under the highlight when there is one, centered otherwise.
  const cardStyle: React.CSSProperties =
    rect !== null
      ? {
          position: "absolute",
          left: Math.min(
            Math.max(rect.left, 16),
            window.innerWidth - 416 - 16,
          ),
          top: rect.bottom + 12,
          width: 400,
        }
      : {
          position: "absolute",
          left: "50%",
          top: "50%",
          transform: "translate(-50%, -50%)",
          width: "min(400px, calc(100vw - 32px))",
        };

  return (
    <div className="fixed inset-0 z-[60]">
      {/* Dim everything, punch no holes: the highlighted rect is
          drawn on top of the dim layer. */}
      <div className="absolute inset-0 bg-black/60 animate-fade-in" />

      {/* Highlight box over the target element. */}
      {rect !== null && (
        <div
          ref={rectRef}
          className="absolute rounded-sm border-2 border-accent bg-transparent transition-all duration-150"
          style={{
            left: rect.left - 4,
            top: rect.top - 4,
            width: rect.width + 8,
            height: rect.height + 8,
            boxShadow: "0 0 0 9999px rgba(0,0,0,0.6)",
          }}
        />
      )}

      {/* Step card. */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label={current.title}
        className={`rounded-sm border border-line bg-bg p-6 ${rect === null ? "animate-scale-in" : "animate-fade-up"}`}
        style={cardStyle}
      >
        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-accent">
          Шаг {step + 1} из {STEPS.length}
        </p>
        <h2 className="mb-3 font-serif text-2xl font-semibold">
          {current.title}
        </h2>
        <p className="mb-6 text-sm leading-relaxed text-fg-muted">
          {current.text}
        </p>
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={onSkip}
            className="text-sm text-fg-muted underline-offset-4 transition-colors duration-150 hover:text-fg hover:underline"
          >
            Пропустить
          </button>
          <div className="flex gap-2">
            {step > 0 && (
              <Button variant="ghost" onClick={() => setStep((s) => s - 1)}>
                Назад
              </Button>
            )}
            <Button
              onClick={() => {
                if (isLast) onComplete();
                else setStep((s) => s + 1);
              }}
            >
              {isLast ? "Начать" : "Далее"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
