export interface ClinicVisitContext {
  patientId: number;
  visitNumber?: string;
  deptId: number;
  waitingId?: number;
  entryDate?: string;
  department?: string | null;
  doctor?: string | null;
  visitDate?: string | null;
  visitTime?: string | null;
  visitType?: string | null;
  visitReason?: string | null;
  visitRoute?: string | null;
  treatmentType?: string | null;
  symptom?: string | null;
  memo?: string | null;
  historyId?: number | null;
}








