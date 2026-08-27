"use client";

import { useState, forwardRef, useImperativeHandle } from "react";
import { Button, Field, Panel } from "@/components/ui";
import styles from "./PatientForm.module.css";
import { post } from "@/services/http/client";

interface PatientData {
  name: string;
  phoneNumber: string;
  identityNumber: string;
  visitNumber: string;
  birth: string;
  gender: string;
}

export type PatientFormData = {
  name: string;
  birthDate: string;
  phone: string;
  identityNumber: string;
  visitNumber: string;
  gender: string;
  address: string;
  symptoms: string;
  notes: string;
};

export interface PatientFormRef {
  getFormData: () => PatientFormData;
  submitPatientData: (customMessage?: string) => Promise<void>;
  resetForm: () => void;
}

const PatientForm = forwardRef<PatientFormRef>((props, ref) => {
  const [formData, setFormData] = useState<PatientFormData>({
    name: "",
    birthDate: "",
    phone: "",
    identityNumber: "",
    visitNumber: "",
    gender: "M",
    address: "",
    symptoms: "",
    notes: "",
  });

  const [isLoading, setIsLoading] = useState(false);

  useImperativeHandle(ref, () => ({
    getFormData: () => formData,
    submitPatientData,
    resetForm,
  }));

  const handleChange = (
    e: React.ChangeEvent<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >
  ) => {
    setFormData((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }));
  };

  const createPatient = async (
    patientData: PatientData
  ): Promise<number | null> => {
    try {
      console.log("환자 등록 요청 시작:", patientData);

      const result = await post<{ patientId: number }>(
        "/api/patients/get_patient_id",
        patientData
      );

      console.log("환자 등록 성공:", result);
      return result.patientId;
    } catch (error) {
      console.error("환자 등록 실패:", error);
      throw error;
    }
  };

  // 폼 초기화 함수
  const resetForm = () => {
    setFormData({
      name: "",
      birthDate: "",
      phone: "",
      identityNumber: "",
      visitNumber: "",
      gender: "M",
      address: "",
      symptoms: "",
      notes: "",
    });
  };

  // 대기 목록 등록 함수
  const registerWaiting = async (patientId: number) => {
    try {
      console.log("대기 목록 등록 시작:", patientId);

      const waitingData = {
        patientId: patientId,
        deptId: 1, // 기본 진료과 ID
        symptom: formData.symptoms || "일반 진료",
        state: "waiting"
      };

      const result = await post("/api/waiting/register", waitingData);
      console.log("대기 등록 성공:", result);
      return result;
    } catch (error) {
      console.error("대기 등록 실패:", error);
      throw error;
    }
  };

  // 환자 등록 로직
  const submitPatientData = async (customMessage?: string) => {
    if (
      !formData.name ||
      !formData.birthDate ||
      !formData.phone ||
      !formData.identityNumber ||
      !formData.visitNumber
    ) {
      alert(
        "필수 정보(환자명, 생년월일, 연락처, 주민등록번호, 내원번호)를 입력해주세요."
      );
      return;
    }

    setIsLoading(true);

    try {
      const patientData: PatientData = {
        name: formData.name,
        phoneNumber: formData.phone,
        identityNumber: formData.identityNumber,
        visitNumber: formData.visitNumber,
        birth: formData.birthDate,
        gender: formData.gender,
      };

      // 환자 등록
      const patientId = await createPatient(patientData);

      if (patientId) {
        // 대기 목록 등록
        try {
          await registerWaiting(patientId);
          const message = customMessage || `환자 정보가 등록되고 대기 목록에 추가되었습니다! (환자 ID: ${patientId})`;
          alert(message);
        } catch {
          // 환자는 등록되었지만 대기 목록 등록 실패
          const message = `환자 정보는 등록되었습니다 (환자 ID: ${patientId})\n하지만 대기 목록 등록에 실패했습니다.`;
          alert(message);
        }
        resetForm();
      }
    } catch {
      alert("환자 등록 중 오류가 발생했습니다. 다시 시도해주세요.");
    } finally {
      setIsLoading(false);
    }
  };




  const fillSampleData = () => {
    setFormData({
      name: "김철수",
      birthDate: "1990-01-01",
      phone: "010-1234-5678",
      identityNumber: "900101-1234567",
      visitNumber: "530524502",
      gender: "M",
      address: "서울시 강남구 테헤란로 123",
      symptoms: "E11",
      notes: "테스트용 환자 데이터 (상병 E11)",
    });
  };

  return (
    <Panel
      className={styles.container}
      title="환자 정보 입력"
      actions={
        <Button type="button" variant="secondary" size="sm" onClick={fillSampleData}>
          샘플 데이터
        </Button>
      }
    >
      <form className={styles.form}>
        <div className={styles.row}>
          <Field label="환자명" htmlFor="patient-name" required>
            <input
              id="patient-name"
              type="text"
              name="name"
              value={formData.name}
              onChange={handleChange}
              required
            />
          </Field>

          <Field label="생년월일" htmlFor="patient-birth-date" required>
            <input
              id="patient-birth-date"
              type="date"
              name="birthDate"
              value={formData.birthDate}
              onChange={handleChange}
              required
            />
          </Field>
        </div>

        <div className={styles.row}>
          <Field label="연락처" htmlFor="patient-phone" required>
            <input
              id="patient-phone"
              type="tel"
              name="phone"
              value={formData.phone}
              onChange={handleChange}
              placeholder="010-0000-0000"
              required
            />
          </Field>

          <Field label="성별" htmlFor="patient-gender" required>
            <select
              id="patient-gender"
              name="gender"
              value={formData.gender}
              onChange={handleChange}
              required
            >
              <option value="M">남성</option>
              <option value="F">여성</option>
            </select>
          </Field>
        </div>

        <Field label="주민등록번호" htmlFor="patient-identity-number" required>
          <input
            id="patient-identity-number"
            type="text"
            name="identityNumber"
            value={formData.identityNumber}
            onChange={handleChange}
            placeholder="000000-0000000"
            required
          />
        </Field>

        <Field label="내원번호" htmlFor="patient-visit-number" required>
          <input
            id="patient-visit-number"
            type="text"
            name="visitNumber"
            value={formData.visitNumber}
            onChange={handleChange}
            placeholder="예: 530524502"
            required
          />
        </Field>

        <Field label="주소" htmlFor="patient-address">
          <input
            id="patient-address"
            type="text"
            name="address"
            value={formData.address}
            onChange={handleChange}
          />
        </Field>

        <Field label="증상" htmlFor="patient-symptoms">
          <textarea
            id="patient-symptoms"
            name="symptoms"
            value={formData.symptoms}
            onChange={handleChange}
            rows={3}
          />
        </Field>
      </form>
    </Panel>
  );
});

PatientForm.displayName = "PatientForm";

export default PatientForm;
