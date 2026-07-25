/**
 * v3 수정 1 — 확장 인적사항 코드 ↔ 한국어 라벨.
 *
 * 저장은 코드(영문)로, 화면은 라벨로. 코드 유니온은 lib/api.ts와 백엔드
 * schemas/auth.py의 Literal과 일치해야 한다. 소득수준·종교는 민감 항목이라
 * "응답 안 함"(prefer_not)을 포함한다(핸드오프 미결 #3).
 */

import type {
  EducationLevel,
  EmploymentStatus,
  HouseholdType,
  IncomeLevel,
  MaritalStatus,
  Religion,
} from "./api";

export type Option<T extends string> = { code: T; label: string };

export const MARITAL_OPTIONS: Option<MaritalStatus>[] = [
  { code: "single", label: "미혼" },
  { code: "married", label: "기혼" },
  { code: "divorced", label: "이혼" },
  { code: "bereaved", label: "사별" },
  { code: "separated", label: "별거" },
  { code: "other", label: "기타" },
];

export const HOUSEHOLD_OPTIONS: Option<HouseholdType>[] = [
  { code: "alone", label: "1인 가구" },
  { code: "spouse", label: "배우자와" },
  { code: "parents", label: "부모와" },
  { code: "children", label: "자녀와" },
  { code: "relatives", label: "친척과" },
  { code: "other", label: "기타" },
];

export const EDUCATION_OPTIONS: Option<EducationLevel>[] = [
  { code: "middle_or_below", label: "중졸 이하" },
  { code: "high_school", label: "고졸" },
  { code: "college", label: "대졸" },
  { code: "graduate", label: "대학원 이상" },
  { code: "other", label: "기타" },
];

export const EMPLOYMENT_OPTIONS: Option<EmploymentStatus>[] = [
  { code: "employed", label: "재직" },
  { code: "self_employed", label: "자영업" },
  { code: "unemployed", label: "무직" },
  { code: "student", label: "학생" },
  { code: "retired", label: "은퇴" },
  { code: "homemaker", label: "주부" },
  { code: "other", label: "기타" },
];

export const INCOME_OPTIONS: Option<IncomeLevel>[] = [
  { code: "low", label: "하" },
  { code: "mid_low", label: "중하" },
  { code: "mid", label: "중" },
  { code: "mid_high", label: "중상" },
  { code: "high", label: "상" },
  { code: "prefer_not", label: "응답 안 함" },
];

export const RELIGION_OPTIONS: Option<Religion>[] = [
  { code: "none", label: "무교" },
  { code: "protestant", label: "개신교" },
  { code: "catholic", label: "천주교" },
  { code: "buddhist", label: "불교" },
  { code: "won", label: "원불교" },
  { code: "other", label: "기타" },
  { code: "prefer_not", label: "응답 안 함" },
];
