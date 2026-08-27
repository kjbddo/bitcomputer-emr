import type { KeyboardEvent } from "react";
import styles from "./Table.module.css";

/**
 * 클릭(또는 더블클릭) 가능한 행/카드에 Enter·Space 키보드 활성화를 붙인다.
 *
 * 다섯 곳(CertificateList, CertificateBottom, CertificatePatientSearch,
 * ViewDataBase, SearchPatientModal)이 동일한 "Enter 또는 Space → preventDefault
 * → 선택 콜백" 로직을 각자 구현하고 있었다. 새로 클릭 가능한 행을 추가할 때
 * 이 헬퍼를 함께 스프레드하면 키보드 경로 누락을 구조적으로 막을 수 있다.
 * <tr> 이 기본이지만, 제네릭으로 다른 요소(TimeLine 의 <article> 카드 등)에도
 * 그대로 쓸 수 있다.
 *
 * 사용: <tr onClick={...} {...rowActivateProps(() => onSelect(item))}>
 */
export function rowActivateProps<T extends HTMLElement = HTMLTableRowElement>(
  onActivate: () => void
): {
  tabIndex: number;
  onKeyDown: (event: KeyboardEvent<T>) => void;
} {
  return {
    tabIndex: 0,
    onKeyDown: (event) => {
      // 행 안의 버튼에서 올라온 키다운은 무시한다.
      //
      // 행에 버튼(보류/완료/삭제 등)이 있으면 그 버튼의 keydown 이 행까지
      // 버블링된다. 여기서 preventDefault 를 부르면 버튼의 기본 활성화가
      // 취소돼 키보드로 버튼을 누를 수 없게 되고, 대신 행 선택이 실행된다.
      // 파괴적 동작(삭제)까지 포함되므로 조용히 넘길 수 없다.
      if (event.target !== event.currentTarget) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onActivate();
      }
    },
  };
}

interface TableProps {
  dense?: boolean;
  stickyHeader?: boolean;
  /**
   * stickyHeader 와 함께 쓴다. .scroll 래퍼의 세로 스크롤포트 높이를 지정해
   * 헤더가 그 안에서 실제로 고정되도록 한다(px 숫자 또는 CSS 길이 문자열).
   * stickyHeader 없이 지정해도 효과가 없다.
   */
  maxHeight?: number | string;
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
  maxHeight,
  className,
  "aria-label": ariaLabel,
  children,
}: TableProps) {
  return (
    <div
      className={[styles.scroll, stickyHeader ? styles.scrollSticky : null]
        .filter(Boolean)
        .join(" ")}
      style={stickyHeader && maxHeight !== undefined ? { maxHeight } : undefined}
    >
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
