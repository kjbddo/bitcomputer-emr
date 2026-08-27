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
});

describe("EmptyState", () => {
  it("title 과 description 을 렌더한다", () => {
    render(<EmptyState title="내역이 없습니다" description="환자를 먼저 선택하세요" />);
    expect(screen.getByText("내역이 없습니다")).toBeInTheDocument();
    expect(screen.getByText("환자를 먼저 선택하세요")).toBeInTheDocument();
  });
});
