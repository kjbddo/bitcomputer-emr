"use client";

import { Panel, Table } from "@/components/ui";
import styles from "./CertificateList.module.css";

export type CertificateType = "general" | "military";

export interface CertificateItem {
  id: number;
  type: CertificateType;
  label: string;
  pdfPath: string;
  patientNumber: string;
  patientName: string;
  age: number;
  department: string;
  doctor: string;
  issueDate: string;
}

interface CertificateListProps {
  selected: CertificateItem | null;
  onSelect: (item: CertificateItem) => void;
}

// TODO: API 연동 시 환자별 진단서 목록으로 교체
const MOCK_CERTIFICATES: CertificateItem[] = [
  {
    id: 1,
    type: "general",
    label: "일반 진단서",
    pdfPath: "/certificates/general.pdf",
    patientNumber: "-",
    patientName: "-",
    age: 0,
    department: "-",
    doctor: "-",
    issueDate: "-",
  },
  {
    id: 2,
    type: "military",
    label: "병무용 진단서",
    pdfPath: "/certificates/military.pdf",
    patientNumber: "-",
    patientName: "-",
    age: 0,
    department: "-",
    doctor: "-",
    issueDate: "-",
  },
];

export default function CertificateList({ selected, onSelect }: CertificateListProps) {
  const handleKeyDown = (event: React.KeyboardEvent<HTMLTableRowElement>, item: CertificateItem) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(item);
    }
  };

  return (
    <Panel
      className={styles.container}
      padding="none"
      title="진단서 목록"
      actions={<span className={styles.count}>{MOCK_CERTIFICATES.length}건</span>}
    >
      <Table>
        <thead>
          <tr>
            <th scope="col">진단서 종류</th>
          </tr>
        </thead>
        <tbody>
          {MOCK_CERTIFICATES.map((item) => (
            <tr
              key={item.id}
              tabIndex={0}
              aria-selected={selected?.id === item.id || undefined}
              onClick={() => onSelect(item)}
              onKeyDown={(event) => handleKeyDown(event, item)}
            >
              <td>{item.label}</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Panel>
  );
}
