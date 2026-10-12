import { useEffect, useState } from "react";

export interface TocItem {
  id: string;
  title: string;
}

/** The chapters in the margin; the one being read is marked. */
export function Toc({ items }: { items: TocItem[] }) {
  const [active, setActive] = useState(items[0]?.id ?? "");
  useEffect(() => {
    const seen = new Map<string, number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) seen.set(e.target.id, e.isIntersecting ? e.boundingClientRect.top : Infinity);
        const visible = [...seen].filter(([, top]) => top !== Infinity).sort((a, b) => a[1] - b[1]);
        if (visible.length) setActive(visible[0][0]);
      },
      { rootMargin: "-20% 0px -55% 0px" },
    );
    for (const it of items) {
      const el = document.getElementById(it.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [items]);
  return (
    <nav className="toc" aria-label="Chapters">
      <a className="toc-name" href="#top">
        Sixth-Finger BCI
      </a>
      <ol>
        {items.map((it, i) => (
          <li key={it.id} data-active={active === it.id ? "" : undefined}>
            <a href={`#${it.id}`}>
              <span className="toc-num">{i + 1}</span>
              {it.title}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
