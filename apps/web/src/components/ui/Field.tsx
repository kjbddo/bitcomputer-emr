import { cloneElement, isValidElement, type ReactElement } from "react";

import styles from "./Field.module.css";

interface FieldProps {
  label: string;
  htmlFor: string;
  error?: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}

interface InjectedControlProps {
  "aria-describedby"?: string;
  required?: boolean;
}

export default function Field({ label, htmlFor, error, hint, required, children }: FieldProps) {
  const errorId = `${htmlFor}-error`;
  const hintId = `${htmlFor}-hint`;
  const describedBy = [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(" ");

  // 입력 요소에 aria-describedby / required 를 주입한다.
  // 호출부가 이미 지정했으면 덮어쓰지 않는다.
  // React 19 의 cloneElement 타입은 두 번째 인자를 element 의 props 타입으로
  // 제한한다. children 은 임의의 ReactNode 이므로 props 형태를 알 수 없어
  // 그대로는 타입을 맞출 수 없다 - 주입하는 속성 형태(InjectedControlProps)로
  // 좁혀서 단언한다. 값 자체는 여전히 아래에서 children.props 를 안전하게
  // 읽어 계산하므로 동작은 바뀌지 않는다.
  const control = isValidElement(children)
    ? cloneElement(children as ReactElement<InjectedControlProps>, {
        "aria-describedby":
          (children.props as InjectedControlProps)["aria-describedby"] ?? (describedBy || undefined),
        required: (children.props as InjectedControlProps).required ?? required,
      })
    : children;

  return (
    <div className={styles.field}>
      {/*
        필수 표시(*)는 label 의 텍스트 자식이 아니라 data-required 를 통한
        CSS ::after 로 렌더한다. @testing-library/dom 의 getByLabelText 는
        aria-hidden 여부와 무관하게 label 의 textContent 를 그대로 이어붙여
        매칭하므로, "*" 를 자식 텍스트로 넣으면 label 텍스트가 "환자명*" 이 되어
        정확히 "환자명" 을 찾는 매칭이 깨진다(실제 브라우저의 accessible name
        계산은 aria-hidden 자식을 제외하지만 테스트 도구는 그렇지 않다).
        CSS 로 생성한 내용은 애초에 DOM 텍스트 노드가 아니므로 label 의
        접근 가능한 이름/텍스트 매칭에 전혀 관여하지 않아 이 문제를 피한다.
      */}
      <label className={styles.label} htmlFor={htmlFor} data-required={required || undefined}>
        {label}
      </label>
      {control}
      {hint && (
        <p className={styles.hint} id={hintId}>
          {hint}
        </p>
      )}
      {error && (
        <p className={styles.error} id={errorId} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
