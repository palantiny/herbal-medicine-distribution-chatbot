const API_BASE = "/api/v1";

export interface HerbItem {
  id: string;
  name: string;
  name_chn: string;
  name_eng: string;
  origin: string;
  price: number;
  stockStatus: "high" | "medium" | "low" | "out";
  qty: number;
  description: string;
  feature: string;
  note: string;
  interaction: string;
  related: string;
  property: string;
  manufacturer: string;
  packagingUnitG: string;
  boxQuantity: string;
  subscriptionPrice: string;
  discountRate: string;
  grade: string;
  marketType: string;
}

export interface HerbDetail extends HerbItem {
  status: string;
  code: string;
  pricePerGeun: string;
  nature: string;
  taste: string;
  meridian: string;
  constitution: string;
  warehouseMaker: string;
  warehouseOrigin: string;
  warehouseDate: string;
  warehouseExpired: string;
}

export async function fetchHerbs(): Promise<{ herbs: HerbItem[]; total: number }> {
  const res = await fetch(`${API_BASE}/herbs`);
  if (!res.ok) throw new Error("약재 목록을 불러오는데 실패했습니다.");
  return res.json();
}

export async function fetchHerbDetail(id: string): Promise<HerbDetail> {
  const res = await fetch(`${API_BASE}/herbs/${id}`);
  if (!res.ok) throw new Error("약재 상세 정보를 불러오는데 실패했습니다.");
  return res.json();
}
