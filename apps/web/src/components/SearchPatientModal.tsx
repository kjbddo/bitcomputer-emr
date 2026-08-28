"use client";

import { ReactNode, useState, useEffect } from "react";
import { Button, EmptyState, Modal, Table, rowActivateProps } from "@/components/ui";
import styles from "./SearchPatientModal.module.css";
import { PatientInfo } from "./PatientInfoBar";
import { get } from "@/services/http/client";

interface Patient {
  id: number;
  name: string;
  phoneNumber: string;
  identityNumber: string;
  visitNumber?: string;
  birth: string;
  gender: string;
}

interface SearchPatientModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  onSelectPatient: (patient: PatientInfo) => void;
  children?: ReactNode;
}

type SearchOption = "전체" | "환자명" | "전화번호" | "생년월일" | "주민등록번호" | "환자번호";

const SEARCH_OPTIONS: SearchOption[] = ["전체", "환자명", "전화번호", "생년월일", "주민등록번호", "환자번호"];

export default function SearchPatientModal({ open, onClose, title, onSelectPatient, children }: SearchPatientModalProps) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [filteredPatients, setFilteredPatients] = useState<Patient[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOption, setSearchOption] = useState<SearchOption>("전체");

  useEffect(() => {
    if (open) {
      fetchAllPatients();
      setSearchQuery(""); // 모달이 열릴 때 검색어 초기화
      setSearchOption("전체"); // 검색 옵션 초기화
    }
  }, [open]);

  useEffect(() => {
    // 검색어가 변경될 때마다 필터링
    if (searchQuery.trim() === "") {
      setFilteredPatients(patients);
    } else {
      const query = searchQuery.toLowerCase().trim();
      const filtered = patients.filter((patient) => {
        // 선택된 옵션에 따라 검색
        switch (searchOption) {
          case "환자명":
            return patient.name.toLowerCase().includes(query);

          case "전화번호":
            const phoneNumber = patient.phoneNumber.replace(/-/g, "");
            return phoneNumber.includes(query.replace(/-/g, ""));

          case "생년월일":
            const birthDate = formatDate(patient.birth).toLowerCase();
            return birthDate.includes(query);

          case "주민등록번호":
            return patient.identityNumber.toLowerCase().includes(query);

          case "환자번호":
            return patient.id.toString().includes(query);

          case "전체":
          default:
            // 전체 검색: 모든 필드에서 검색
            if (patient.name.toLowerCase().includes(query)) return true;
            const phone = patient.phoneNumber.replace(/-/g, "");
            if (phone.includes(query.replace(/-/g, ""))) return true;
            const birth = formatDate(patient.birth).toLowerCase();
            if (birth.includes(query)) return true;
            if (patient.identityNumber.toLowerCase().includes(query)) return true;
            if (patient.id.toString().includes(query)) return true;
            return false;
        }
      });
      setFilteredPatients(filtered);
    }
  }, [searchQuery, searchOption, patients]);

  const fetchAllPatients = async () => {
    try {
      setIsLoading(true);
      const data = await get<Patient[]>("/api/patients/get_all");
      setPatients(data);
      setFilteredPatients(data); // 초기에는 모든 환자 표시
    } catch (error) {
      console.error("환자 목록 조회 실패:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString("ko-KR", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).replace(/\./g, '-').replace(/ /g, '').slice(0, -1);
    } catch {
      return dateString;
    }
  };

  const calculateAgeWithMonths = (birthString: string) => {
    if (!birthString) return "-";
    const birth = new Date(birthString);
    if (Number.isNaN(birth.getTime())) return "-";

    const today = new Date();
    let years = today.getFullYear() - birth.getFullYear();
    let months = today.getMonth() - birth.getMonth();

    if (today.getDate() < birth.getDate()) {
      months -= 1;
    }

    if (months < 0) {
      years -= 1;
      months += 12;
    }

    const ageText = `${years}세`;
    return months > 0 ? `${ageText} ${months}개월` : ageText;
  };

  const handlePatientSelect = (patient: Patient) => {
    const selectedPatient: PatientInfo = {
      patientId: patient.id?.toString(),
      visitNumber: patient.visitNumber,
      name: patient.name,
      age: calculateAgeWithMonths(patient.birth),
      gender: patient.gender,
      doctor: "-",
      date: "-",
      time: "-",
      address: "-",
      phone: patient.phoneNumber,
    };

    onSelectPatient(selectedPatient);
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} title={title} size="lg">
      <div className={styles.searchSection}>
        <select
          className={styles.searchOption}
          aria-label="검색 조건"
          value={searchOption}
          onChange={(e) => setSearchOption(e.target.value as SearchOption)}
        >
          {SEARCH_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <input
          type="text"
          className={styles.searchInput}
          placeholder={searchOption === "전체"
            ? "검색어를 입력하세요"
            : `${searchOption}으로 검색`}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        {searchQuery && (
          <Button type="button" variant="ghost" size="sm" onClick={() => setSearchQuery("")}>
            지우기
          </Button>
        )}
      </div>

      {isLoading ? (
        <EmptyState title="환자 목록을 불러오는 중..." />
      ) : (
        <>
          {searchQuery && (
            <p className={styles.searchResultInfo}>검색 결과: {filteredPatients.length}명</p>
          )}
          {filteredPatients.length === 0 ? (
            <EmptyState
              title={searchQuery ? "검색 결과가 없습니다." : "등록된 환자가 없습니다."}
            />
          ) : (
            <Table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">최근내원일</th>
                  <th scope="col">환자명</th>
                  <th scope="col">성별</th>
                  <th scope="col">생년월일</th>
                  <th scope="col">전화번호</th>
                  <th scope="col">진료과</th>
                  <th scope="col">담당의사</th>
                  <th scope="col">환자 번호</th>
                </tr>
              </thead>
              <tbody>
                {filteredPatients.map((patient) => (
                  <tr
                    key={patient.id}
                    onClick={() => handlePatientSelect(patient)}
                    {...rowActivateProps(() => handlePatientSelect(patient))}
                  >
                    <td>-</td>
                    <td>{patient.name}</td>
                    <td>{patient.gender === 'M' ? '남' : patient.gender === 'F' ? '여' : '-'}</td>
                    <td>{formatDate(patient.birth)}</td>
                    <td>{patient.phoneNumber}</td>
                    <td>-</td>
                    <td>-</td>
                    <td>{patient.id}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </>
      )}
      {children}
    </Modal>
  );
}
