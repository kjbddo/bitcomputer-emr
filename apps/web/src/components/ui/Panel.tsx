import styles from "./Panel.module.css";

interface PanelProps {
  title?: React.ReactNode;
  actions?: React.ReactNode;
  footer?: React.ReactNode;
  padding?: "none" | "md";
  className?: string;
  children: React.ReactNode;
}

export default function Panel({
  title,
  actions,
  footer,
  padding = "md",
  className,
  children,
}: PanelProps) {
  return (
    <section className={[styles.panel, className].filter(Boolean).join(" ")}>
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
