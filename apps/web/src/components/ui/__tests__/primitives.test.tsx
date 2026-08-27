import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent } from "@testing-library/react";

import { Badge, Button, EmptyState, Field, Panel, Table, rowActivateProps } from "../index";

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

  // 이름 없는 <section> 은 ARIA 랜드마크로 계산되지 않는다. 이관 전 자체 셸이
  // aria-label 을 갖고 있던 컴포넌트(TimeLine)가 그것을 잃지 않도록 통과시킨다.
  it("aria-label 을 section 에 전달해 region 랜드마크가 되게 한다", () => {
    render(
      <Panel aria-label="환자 내원 타임라인" title="내원정보 TimeLine">
        본문
      </Panel>
    );
    expect(screen.getByRole("region", { name: "환자 내원 타임라인" })).toBeInTheDocument();
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

describe("Field", () => {
  it("라벨을 입력에 연결한다", () => {
    render(
      <Field label="환자명" htmlFor="patient-name">
        <input id="patient-name" />
      </Field>
    );
    expect(screen.getByLabelText("환자명")).toBeInTheDocument();
  });

  it("error 를 alert 로 노출하고 aria-describedby 로 연결한다", () => {
    render(
      <Field label="환자명" htmlFor="patient-name" error="필수 항목입니다">
        <input id="patient-name" />
      </Field>
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("필수 항목입니다");
    expect(screen.getByLabelText("환자명")).toHaveAttribute("aria-describedby", alert.id);
  });

  it("required 면 입력에 required 를 전달한다", () => {
    render(
      <Field label="환자명" htmlFor="patient-name" required>
        <input id="patient-name" />
      </Field>
    );
    expect(screen.getByLabelText("환자명")).toBeRequired();
  });
});

describe("Table 행 활성화", () => {
  // 행에 버튼이 있으면 버튼의 keydown 이 행까지 버블링된다. 행 핸들러가
  // preventDefault 를 부르면 버튼이 키보드로 눌리지 않고 대신 행이 선택된다.
  // WaitingStatus 의 보류/완료/삭제 버튼에서 실제로 발생했던 회귀다.
  it("행 안 버튼에서 올라온 Enter 는 행 활성화를 일으키지 않는다", () => {
    const onActivate = vi.fn();
    const onButton = vi.fn();
    render(
      <Table>
        <tbody>
          <tr {...rowActivateProps(onActivate)}>
            <td>
              <button type="button" onClick={onButton}>
                삭제
              </button>
            </td>
          </tr>
        </tbody>
      </Table>
    );
    fireEvent.keyDown(screen.getByRole("button", { name: "삭제" }), { key: "Enter" });
    expect(onActivate).not.toHaveBeenCalled();
  });

  it("행 자신에서 누른 Enter 는 행을 활성화한다", () => {
    const onActivate = vi.fn();
    render(
      <Table>
        <tbody>
          <tr {...rowActivateProps(onActivate)}>
            <td>내용</td>
          </tr>
        </tbody>
      </Table>
    );
    fireEvent.keyDown(screen.getByRole("row"), { key: "Enter" });
    expect(onActivate).toHaveBeenCalledTimes(1);
  });
});

describe("Table", () => {
  // 목록 위젯을 표로 승격할 때 원래 위젯의 aria-label 을 잃는 사고가 실제로 났다.
  it("aria-label 을 table 에 전달한다", () => {
    render(
      <Table aria-label="진료 이력">
        <tbody>
          <tr>
            <td>행</td>
          </tr>
        </tbody>
      </Table>
    );
    expect(screen.getByRole("table", { name: "진료 이력" })).toBeInTheDocument();
  });


  it("table 시맨틱을 유지한다", () => {
    render(
      <Table>
        <thead>
          <tr>
            <th scope="col">이름</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>김환자</td>
          </tr>
        </tbody>
      </Table>
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "이름" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "김환자" })).toBeInTheDocument();
  });

  it("table 을 스크롤 가능한 wrapper div 로 감싼다", () => {
    const { container } = render(
      <Table>
        <tbody>
          <tr>
            <td>행</td>
          </tr>
        </tbody>
      </Table>
    );
    const table = screen.getByRole("table");
    const wrapper = table.parentElement;
    expect(wrapper).not.toBeNull();
    expect(wrapper).not.toBe(container);
    expect(wrapper?.tagName).toBe("DIV");
  });

  it("dense 는 table 에 별도 class 를 붙인다", () => {
    const { rerender } = render(
      <Table>
        <tbody>
          <tr>
            <td>행</td>
          </tr>
        </tbody>
      </Table>
    );
    const plainClass = screen.getByRole("table").className;

    rerender(
      <Table dense>
        <tbody>
          <tr>
            <td>행</td>
          </tr>
        </tbody>
      </Table>
    );
    const denseClass = screen.getByRole("table").className;
    expect(denseClass).not.toBe(plainClass);
  });

  it("className 을 table 에 전달한다", () => {
    render(
      <Table className="custom-table">
        <tbody>
          <tr>
            <td>행</td>
          </tr>
        </tbody>
      </Table>
    );
    expect(screen.getByRole("table").className).toContain("custom-table");
  });

  // stickyHeader 는 헤더가 실제로 화면에 고정되는지가 핵심이라, position: sticky
  // 가 걸린 조상이 아니라 그 sticky 가 기준으로 삼는 스크롤 컨테이너 자체가
  // Table 내부(.scroll)에 있는지를 확인한다. 이 스크롤 컨테이너가 외부 래퍼로
  // 새어나가면(예: 부모가 별도로 overflow-y:auto 박스를 두면) 두 스크롤
  // 컨테이너가 경합해 헤더가 고정되지 않는다(리뷰에서 확인된 실제 버그).
  it("stickyHeader + maxHeight 는 wrapper 를 세로 스크롤 컨테이너로 만든다", () => {
    render(
      <Table stickyHeader maxHeight={120}>
        <thead>
          <tr>
            <th>이름</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>행</td>
          </tr>
        </tbody>
      </Table>
    );
    const wrapper = screen.getByRole("table").parentElement as HTMLElement;
    expect(wrapper.style.maxHeight).toBe("120px");
    expect(wrapper.className).toContain("scrollSticky");
  });

  it("stickyHeader 없이 maxHeight 를 줘도 효과가 없다", () => {
    render(
      <Table maxHeight={120}>
        <tbody>
          <tr>
            <td>행</td>
          </tr>
        </tbody>
      </Table>
    );
    const wrapper = screen.getByRole("table").parentElement as HTMLElement;
    expect(wrapper.style.maxHeight).toBe("");
  });
});

describe("rowActivateProps", () => {
  it("Enter 키에서 preventDefault 하고 콜백을 호출한다", () => {
    const onActivate = vi.fn();
    render(
      <table>
        <tbody>
          <tr data-testid="row" {...rowActivateProps(onActivate)}>
            <td>행</td>
          </tr>
        </tbody>
      </table>
    );
    const row = screen.getByTestId("row");
    expect(row).toHaveAttribute("tabIndex", "0");
    fireEvent.keyDown(row, { key: "Enter" });
    expect(onActivate).toHaveBeenCalledTimes(1);
  });

  it("Space 키에서도 콜백을 호출한다", () => {
    const onActivate = vi.fn();
    render(
      <table>
        <tbody>
          <tr data-testid="row" {...rowActivateProps(onActivate)}>
            <td>행</td>
          </tr>
        </tbody>
      </table>
    );
    fireEvent.keyDown(screen.getByTestId("row"), { key: " " });
    expect(onActivate).toHaveBeenCalledTimes(1);
  });

  it("다른 키에서는 콜백을 호출하지 않는다", () => {
    const onActivate = vi.fn();
    render(
      <table>
        <tbody>
          <tr data-testid="row" {...rowActivateProps(onActivate)}>
            <td>행</td>
          </tr>
        </tbody>
      </table>
    );
    fireEvent.keyDown(screen.getByTestId("row"), { key: "ArrowDown" });
    expect(onActivate).not.toHaveBeenCalled();
  });
});
