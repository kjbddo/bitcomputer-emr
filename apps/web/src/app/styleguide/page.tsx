"use client";

import { useState } from "react";
import { notFound } from "next/navigation";

import { Badge, Button, EmptyState, Field, Modal, Panel, Table, ThemeToggle } from "@/components/ui";
import styles from "./page.module.css";

const SURFACE_TOKENS = [
  "surface-canvas",
  "surface-sunken",
  "surface-raised",
  "surface-overlay",
  "surface-chrome",
  "surface-chrome-hover",
  "surface-chrome-active",
];

const TEXT_TOKENS = ["text-primary", "text-secondary", "text-muted", "text-on-chrome"];

// text-on-chrome 은 밝은 표면이 아니라 chrome 표면 위에서 쓰도록 설계된 토큰이므로,
// 견본도 실제 사용 맥락(surface-chrome)에 맞춰 배경을 바꿔 보여준다.
const TEXT_TOKEN_BG: Record<string, string> = {
  "text-on-chrome": "surface-chrome",
};

const ROLE_PAIRS: Array<[string, string]> = [
  ["accent-bg", "accent-text"],
  ["success-bg", "success-text"],
  ["warning-bg", "warning-text"],
  ["danger-bg", "danger-text"],
];

const CLINIC_STATES = [
  { label: "대기", tone: "accent" as const },
  { label: "진료중", tone: "warning" as const },
  { label: "완료", tone: "success" as const },
  { label: "취소", tone: "danger" as const },
];

const QUEUE_ROWS = [
  { id: "1", name: "김민준", time: "09:20", tone: "accent" as const, label: "대기" },
  { id: "2", name: "이서연", time: "09:35", tone: "warning" as const, label: "진료중" },
  { id: "3", name: "박도윤", time: "09:50", tone: "success" as const, label: "완료" },
  { id: "4", name: "최지우", time: "10:05", tone: "danger" as const, label: "취소" },
  { id: "5", name: "정하윤", time: "10:20", tone: "accent" as const, label: "대기" },
  { id: "6", name: "강서준", time: "10:35", tone: "accent" as const, label: "대기" },
  { id: "7", name: "윤지호", time: "10:50", tone: "warning" as const, label: "진료중" },
];

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={styles.section}>
      <h2 className={styles.sectionTitle}>{title}</h2>
      {description && <p className={styles.sectionDescription}>{description}</p>}
      <div className={styles.row}>{children}</div>
    </section>
  );
}

export default function StyleguidePage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  const [openSize, setOpenSize] = useState<"sm" | "md" | "lg" | null>(null);

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <h1>디자인 시스템 스타일가이드</h1>
        <ThemeToggle />
      </header>

      <Section
        title="Button"
        description="variant 4종 × size 2종 × (기본 / loading / disabled)"
      >
        {(["primary", "secondary", "ghost", "danger"] as const).map((variant) =>
          (["md", "sm"] as const).map((size) => (
            <div key={`${variant}-${size}`} className={styles.cell}>
              <span className={styles.cellLabel}>
                {variant} / {size}
              </span>
              <Button variant={variant} size={size}>
                {variant}
              </Button>
              <Button variant={variant} size={size} loading>
                loading
              </Button>
              <Button variant={variant} size={size} disabled>
                disabled
              </Button>
            </div>
          ))
        )}
      </Section>

      <Section title="Badge" description="tone 5종">
        {(["neutral", "accent", "success", "warning", "danger"] as const).map((tone) => (
          <Badge key={tone} tone={tone}>
            {tone}
          </Badge>
        ))}
      </Section>

      <Section title="임상 상태" description="spec §4.2 매핑: 대기(accent) / 진료중(warning) / 완료(success) / 취소(danger)">
        {CLINIC_STATES.map((state) => (
          <Badge key={state.label} tone={state.tone}>
            {state.label}
          </Badge>
        ))}
      </Section>

      <Section title="Panel" description="title 없음 / title 있음 / actions 있음 / padding=none + Table">
        <div className={styles.grid}>
          <Panel>
            <p className={styles.bodyText}>title 이 없으면 헤더 자체가 렌더되지 않는다.</p>
          </Panel>

          <Panel title="환자 대기 현황">
            <p className={styles.bodyText}>title 만 있는 기본 패널이다.</p>
          </Panel>

          <Panel
            title="처방 목록"
            actions={
              <Button variant="secondary" size="sm">
                새로고침
              </Button>
            }
          >
            <p className={styles.bodyText}>actions 슬롯에 보조 동작 버튼을 배치한다.</p>
          </Panel>

          <Panel title="대기 목록 (padding=none)" padding="none">
            <Table>
              <thead>
                <tr>
                  <th>이름</th>
                  <th>시간</th>
                </tr>
              </thead>
              <tbody>
                {QUEUE_ROWS.slice(0, 3).map((row) => (
                  <tr key={row.id}>
                    <td>{row.name}</td>
                    <td>{row.time}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Panel>
        </div>
      </Section>

      <Section title="Field" description="기본 / hint / error / required">
        <form className={styles.form} onSubmit={(event) => event.preventDefault()}>
          <Field label="환자명" htmlFor="field-plain">
            <input id="field-plain" className={styles.input} placeholder="예: 홍길동" />
          </Field>

          <Field label="연락처" htmlFor="field-hint" hint="'-' 없이 숫자만 입력합니다.">
            <input id="field-hint" className={styles.input} placeholder="01012345678" />
          </Field>

          <Field label="주민등록번호" htmlFor="field-error" error="형식이 올바르지 않습니다.">
            <input id="field-error" className={styles.input} defaultValue="000000-0000000" />
          </Field>

          <Field label="진료과" htmlFor="field-required" required>
            <input id="field-required" className={styles.input} placeholder="예: 내과" />
          </Field>
        </form>
      </Section>

      <Section title="Table" description="기본 / dense / stickyHeader / 선택 행(aria-selected)">
        <div className={styles.grid}>
          <Panel title="기본" padding="none">
            <Table>
              <thead>
                <tr>
                  <th>이름</th>
                  <th>시간</th>
                  <th>상태</th>
                </tr>
              </thead>
              <tbody>
                {QUEUE_ROWS.slice(0, 4).map((row) => (
                  <tr key={row.id}>
                    <td>{row.name}</td>
                    <td>{row.time}</td>
                    <td>
                      <Badge tone={row.tone}>{row.label}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Panel>

          <Panel title="dense" padding="none">
            <Table dense>
              <thead>
                <tr>
                  <th>이름</th>
                  <th>시간</th>
                  <th>상태</th>
                </tr>
              </thead>
              <tbody>
                {QUEUE_ROWS.slice(0, 4).map((row) => (
                  <tr key={row.id}>
                    <td>{row.name}</td>
                    <td>{row.time}</td>
                    <td>
                      <Badge tone={row.tone}>{row.label}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Panel>

          <Panel title="stickyHeader (스크롤하며 확인)" padding="none">
            <div className={styles.tableScrollBox}>
              <Table stickyHeader>
                <thead>
                  <tr>
                    <th>이름</th>
                    <th>시간</th>
                    <th>상태</th>
                  </tr>
                </thead>
                <tbody>
                  {QUEUE_ROWS.map((row) => (
                    <tr key={row.id}>
                      <td>{row.name}</td>
                      <td>{row.time}</td>
                      <td>
                        <Badge tone={row.tone}>{row.label}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          </Panel>

          <Panel title="선택 행(aria-selected)" padding="none">
            <Table>
              <thead>
                <tr>
                  <th>이름</th>
                  <th>시간</th>
                  <th>상태</th>
                </tr>
              </thead>
              <tbody>
                {QUEUE_ROWS.slice(0, 4).map((row) => (
                  <tr key={row.id} aria-selected={row.id === "2" || undefined}>
                    <td>{row.name}</td>
                    <td>{row.time}</td>
                    <td>
                      <Badge tone={row.tone}>{row.label}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Panel>
        </div>
      </Section>

      <Section title="Modal" description="sm / md / lg — 열기 버튼으로 각각 확인">
        {(["sm", "md", "lg"] as const).map((size) => (
          <Button key={size} onClick={() => setOpenSize(size)}>
            {size} 열기
          </Button>
        ))}
        <Modal
          open={openSize !== null}
          onClose={() => setOpenSize(null)}
          title={`모달 ${openSize ?? ""}`}
          size={openSize ?? "md"}
          footer={
            <Button variant="primary" onClick={() => setOpenSize(null)}>
              확인
            </Button>
          }
        >
          <p className={styles.bodyText}>
            Escape 로 닫히고, 닫힌 뒤 포커스가 방금 클릭한 열기 버튼으로 돌아오는지 확인한다. 탭
            이동이 모달 내부에서만 순환하는지(포커스 트랩)도 함께 확인한다.
          </p>
        </Modal>
      </Section>

      <Section title="EmptyState" description="description 있음 / action 있음">
        <div className={styles.grid}>
          <Panel>
            <EmptyState title="검색 결과가 없습니다" description="다른 조건으로 다시 검색해보세요." />
          </Panel>
          <Panel>
            <EmptyState
              title="등록된 처방이 없습니다"
              action={<Button variant="primary">처방 추가</Button>}
            />
          </Panel>
        </div>
      </Section>

      <Section title="표면 토큰 (surface)">
        {SURFACE_TOKENS.map((token) => (
          <div key={token} className={styles.swatchGroup}>
            <div className={styles.swatch} style={{ background: `var(--${token})` }} />
            <span className={styles.swatchLabel}>--{token}</span>
          </div>
        ))}
      </Section>

      <Section title="텍스트 토큰 (text)">
        {TEXT_TOKENS.map((token) => (
          <div key={token} className={styles.swatchGroup}>
            <div
              className={styles.textSample}
              style={{
                background: `var(--${TEXT_TOKEN_BG[token] ?? "surface-raised"})`,
                color: `var(--${token})`,
              }}
            >
              Aa 가나다
            </div>
            <span className={styles.swatchLabel}>--{token}</span>
          </div>
        ))}
      </Section>

      <Section title="역할 토큰 쌍 (bg / text)">
        {ROLE_PAIRS.map(([bg, text]) => (
          <div key={bg} className={styles.swatchGroup}>
            <div
              className={styles.roleSample}
              style={{ background: `var(--${bg})`, color: `var(--${text})` }}
            >
              Aa 가나다
            </div>
            <span className={styles.swatchLabel}>
              --{bg} / --{text}
            </span>
          </div>
        ))}
      </Section>
    </div>
  );
}
