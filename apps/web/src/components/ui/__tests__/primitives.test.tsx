import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Badge, Button, EmptyState, Panel } from "../index";

describe("Panel", () => {
  it("title 을 헤딩으로 렌더한다", () => {
    render(<Panel title="대기 현황">본문</Panel>);
    expect(screen.getByRole("heading", { name: "대기 현황" })).toBeInTheDocument();
    expect(screen.getByText("본문")).toBeInTheDocument();
  });

  it("title 이 없으면 헤딩을 만들지 않는다", () => {
    render(<Panel>본문만</Panel>);
    expect(screen.queryByRole("heading")).toBeNull();
  });

  it("actions 를 렌더한다", () => {
    render(<Panel title="목록" actions={<button type="button">추가</button>}>본문</Panel>);
    expect(screen.getByRole("button", { name: "추가" })).toBeInTheDocument();
  });

  it("title 없이 actions 만 있어도 actions 를 렌더한다", () => {
    render(<Panel actions={<button type="button">새로고침</button>}>본문</Panel>);
    expect(screen.getByRole("button", { name: "새로고침" })).toBeInTheDocument();
    expect(screen.queryByRole("heading")).toBeNull();
  });
});

describe("Button", () => {
  it("type 기본값이 button 이다", () => {
    render(<Button>저장</Button>);
    expect(screen.getByRole("button", { name: "저장" })).toHaveAttribute("type", "button");
  });

  it("loading 이면 비활성이고 접근성 이름을 유지한다", () => {
    render(<Button loading>분석</Button>);
    const button = screen.getByRole("button", { name: "분석" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("전달한 type 을 덮어쓰지 않는다", () => {
    render(<Button type="submit">제출</Button>);
    expect(screen.getByRole("button", { name: "제출" })).toHaveAttribute("type", "submit");
  });
});

describe("Badge", () => {
  it("내용을 렌더한다", () => {
    render(<Badge tone="warning">stub</Badge>);
    expect(screen.getByText("stub")).toBeInTheDocument();
  });

  // tone 을 무시하는 스텁 구현도 위 테스트는 통과한다. tone 이 실제로
  // 표현에 반영되는지는 서로 다른 tone 의 class 가 달라지는 것으로 확인한다.
  // 특정 class 이름에 결합하지 않으려고 값 비교 대신 차이만 단언한다.
  it("tone 마다 다른 class 를 붙인다", () => {
    const { container } = render(
      <>
        <Badge tone="success">완료</Badge>
        <Badge tone="danger">거부</Badge>
        <Badge>기본</Badge>
      </>
    );
    const classNames = Array.from(container.querySelectorAll("span")).map((el) => el.className);
    expect(classNames).toHaveLength(3);
    expect(new Set(classNames).size).toBe(3);
  });
});

describe("EmptyState", () => {
  it("title 과 description 을 렌더한다", () => {
    render(<EmptyState title="내역이 없습니다" description="환자를 먼저 선택하세요" />);
    expect(screen.getByText("내역이 없습니다")).toBeInTheDocument();
    expect(screen.getByText("환자를 먼저 선택하세요")).toBeInTheDocument();
  });
});
