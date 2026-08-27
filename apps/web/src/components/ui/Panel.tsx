import styles from "./Panel.module.css";

interface PanelProps {
  title?: React.ReactNode;
  actions?: React.ReactNode;
  footer?: React.ReactNode;
  padding?: "none" | "md";
  className?: string;
  /**
   * <section> 에 접근성 이름을 붙여 ARIA region 랜드마크로 만든다.
   *
   * 이름 없는 <section> 은 랜드마크로 계산되지 않는다. 이관 전에 자체 셸이
   * aria-label 을 갖고 있던 컴포넌트는 이 prop 으로 그것을 유지해야 한다.
   * title 을 그대로 쓰면 되는 경우가 대부분이므로 기본값으로 강제하지는 않는다 —
   * 화면마다 패널이 여러 개라 전부 랜드마크가 되면 오히려 탐색이 시끄러워진다.
   */
  "aria-label"?: string;
  children: React.ReactNode;
}

export default function Panel({
  title,
  actions,
  footer,
  padding = "md",
  className,
  "aria-label": ariaLabel,
  children,
}: PanelProps) {
  return (
    <section
      className={[styles.panel, className].filter(Boolean).join(" ")}
      aria-label={ariaLabel}
    >
      {(title || actions) && (
        <div className={styles.header}>
          {title && <h2 className={styles.title}>{title}</h2>}
          {actions && <div className={styles.actions}>{actions}</div>}
        </div>
      )}
      <div className={padding === "none" ? styles.bodyFlush : styles.body}>{children}</div>
      {footer && <div className={styles.footer}>{footer}</div>}
    </section>
  );
}
