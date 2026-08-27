import styles from "./Button.module.css";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const VARIANT_CLASS: Record<Variant, string> = {
  primary: styles.primary,
  secondary: styles.secondary,
  ghost: styles.ghost,
  danger: styles.danger,
};

const SIZE_CLASS: Record<Size, string> = {
  sm: styles.sm,
  md: styles.md,
};

export default function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  disabled,
  className,
  type,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      // type 을 명시하지 않으면 폼 안에서 의도치 않게 submit 된다.
      type={type ?? "button"}
      className={[styles.button, VARIANT_CLASS[variant], SIZE_CLASS[size], className]
        .filter(Boolean)
        .join(" ")}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && <span className={styles.spinner} aria-hidden="true" />}
      {children}
    </button>
  );
}
