import styles from "./Table.module.css";

interface TableProps {
  dense?: boolean;
  stickyHeader?: boolean;
  className?: string;
  children: React.ReactNode;
}

export default function Table({ dense, stickyHeader, className, children }: TableProps) {
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
      >
        {children}
      </table>
    </div>
  );
}
