"use client";

import { useEffect, useState, forwardRef, useImperativeHandle } from "react";
import { getDoctors, type DoctorProfile } from "@/services/auth";
import { Field, Panel } from "@/components/ui";
import styles from "./MedicalInfo.module.css";

export type MedicalInfoFormData = {
  department: string;
  doctor: string;
  visitDate: string;
  visitTime: string;
  visitType: string;
  visitReason: string;
  visitRoute: string;
  treatmentType: string;
  memo: string;
};

export interface MedicalInfoRef {
  getFormData: () => MedicalInfoFormData;
  resetForm: () => void;
}

const MedicalInfo = forwardRef<MedicalInfoRef>((props, ref) => {
  const getToday = () => new Date().toISOString().slice(0, 10);
  const getCurrentTime = () => {
    const now = new Date();
    return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  };
  const [formData, setFormData] = useState<MedicalInfoFormData>({
    department: "검진",
    doctor: "",
    visitDate: getToday(),
    visitTime: getCurrentTime(),
    visitType: "재진",
    visitReason: "",
    visitRoute: "",
    treatmentType: "",
    memo: "",
  });
  const [doctors, setDoctors] = useState<DoctorProfile[]>([]);

  useEffect(() => {
    let ignore = false;
    async function loadDoctors() {
      try {
        const rows = await getDoctors();
        if (ignore) return;
        setDoctors(rows);
        setFormData((prev) => ({
          ...prev,
          doctor: prev.doctor || rows[0]?.name || "",
        }));
      } catch (error) {
        console.error("진료의사 목록 조회 실패", error);
      }
    }
    void loadDoctors();
    return () => {
      ignore = true;
    };
  }, []);

  const handleInputChange = (
    e: React.ChangeEvent<
      HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
    >
  ) => {
    setFormData((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }));
  };

  const resetForm = () => {
    setFormData({
      department: "검진",
      doctor: doctors[0]?.name || "",
      visitDate: getToday(),
      visitTime: getCurrentTime(),
      visitType: "재진",
      visitReason: "",
      visitRoute: "",
      treatmentType: "",
      memo: "",
    });
  };

  useImperativeHandle(ref, () => ({
    getFormData: () => formData,
    resetForm,
  }));

  return (
    <Panel className={styles.container} title="진료정보">
      <form className={styles.form}>
        <div className={styles.row}>
          <Field label="진료과목" htmlFor="medical-department" required>
            <select
              id="medical-department"
              name="department"
              value={formData.department}
              onChange={handleInputChange}
            >
              <option value="검진">검진</option>
              <option value="내과">내과</option>
              <option value="정형외과">정형외과</option>
            </select>
          </Field>

          <Field label="진료의사" htmlFor="medical-doctor" required>
            <select
              id="medical-doctor"
              name="doctor"
              value={formData.doctor}
              onChange={handleInputChange}
            >
              {doctors.length === 0 ? (
                <option value="">등록된 의사 없음</option>
              ) : (
                doctors.map((doctor) => (
                  <option key={doctor.id} value={doctor.name}>
                    {doctor.name}
                  </option>
                ))
              )}
            </select>
          </Field>
        </div>

        <div className={styles.row}>
          <Field label="진료일" htmlFor="medical-visit-date" required>
            <input
              id="medical-visit-date"
              type="date"
              name="visitDate"
              value={formData.visitDate}
              onChange={handleInputChange}
            />
          </Field>

          <Field label="접수시간" htmlFor="medical-visit-time" required>
            <input
              id="medical-visit-time"
              type="time"
              name="visitTime"
              value={formData.visitTime}
              onChange={handleInputChange}
            />
          </Field>
        </div>

        <div className={styles.row}>
          <Field label="초/재진" htmlFor="medical-visit-type">
            <select
              id="medical-visit-type"
              name="visitType"
              value={formData.visitType}
              onChange={handleInputChange}
            >
              <option value="재진">재진</option>
              <option value="초진">초진</option>
            </select>
          </Field>

          <Field label="내원사유" htmlFor="medical-visit-reason">
            <input
              id="medical-visit-reason"
              type="text"
              name="visitReason"
              value={formData.visitReason}
              onChange={handleInputChange}
            />
          </Field>
        </div>

        <div className={styles.row}>
          <Field label="내원경로" htmlFor="medical-visit-route">
            <select
              id="medical-visit-route"
              name="visitRoute"
              value={formData.visitRoute}
              onChange={handleInputChange}
            >
              <option value="">선택</option>
              <option value="직접내원">직접내원</option>
              <option value="타병원의뢰">타병원의뢰</option>
            </select>
          </Field>

          <Field label="진료유형" htmlFor="medical-treatment-type">
            <select
              id="medical-treatment-type"
              name="treatmentType"
              value={formData.treatmentType}
              onChange={handleInputChange}
            >
              <option value="">선택</option>
              <option value="일반진료">일반진료</option>
              <option value="응급진료">응급진료</option>
            </select>
          </Field>
        </div>

        <Field label="당일메모" htmlFor="medical-memo">
          <textarea
            id="medical-memo"
            name="memo"
            value={formData.memo}
            onChange={handleInputChange}
            rows={4}
          />
        </Field>
      </form>
    </Panel>
  );
});

MedicalInfo.displayName = "MedicalInfo";

export default MedicalInfo;
