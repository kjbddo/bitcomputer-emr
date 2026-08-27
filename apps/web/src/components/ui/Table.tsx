import styles from "./Table.module.css";

interface TableProps {
  dense?: boolean;
  stickyHeader?: boolean;
  className?: string;
  /**
   * 표에 접근성 이름을 붙인다.
   *
   * 이름 없는 <table> 은 스크린리더가 "표"라고만 읽는다. 목록 위젯을 표로
   * 승격할 때 원래 위젯이 갖고 있던 aria-label 을 여기로 넘겨야 이름을 잃지 않는다.
   */
  "aria-label"?: string;
  children: React.ReactNode;
}

export default function Table({
  dense,
  stickyHeader,
  className,
  "aria-label": ariaLabel,
  children,
}: TableProps) {
  return (
    <div className={styles.scroll}>
      <table
        className={[
          styles.table,
          dense ? styles.dense : null,
          stickyHeader ? styles.sticky : null,
          className,
        ]
          .filter(Boolean)
          .join(" ")}
        aria-label={ariaLabel}
      >
        {children}
      </table>
    </div>
  );
}
