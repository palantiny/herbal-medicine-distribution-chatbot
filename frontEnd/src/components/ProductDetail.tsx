import { Link } from 'react-router';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { ArrowLeft, ShoppingCart, Heart, User, Bell, Search, FileText, Plus, Minus, Package, ChevronRight, Truck, CheckCircle2, Loader2, Leaf } from 'lucide-react';
import { ChatbotButton } from './ChatbotButton';
import { useState, useEffect } from 'react';
import { useParams } from 'react-router';
import { fetchHerbDetail, type HerbDetail as HerbDetailType } from '../api';

const stockStatusConfig: Record<string, { label: string; color: string }> = {
  high: { label: '충분', color: 'text-[#059669]' },
  medium: { label: '보통', color: 'text-yellow-600' },
  low: { label: '부족', color: 'text-orange-600' },
  out: { label: '품절', color: 'text-red-600' },
};

export function ProductDetail() {
  const { id } = useParams();
  const [herb, setHerb] = useState<HerbDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    fetchHerbDetail(id)
      .then((data) => {
        setHerb(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [id]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F9FAFB] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-[#059669]" />
        <span className="ml-3 text-gray-500">약재 정보를 불러오는 중...</span>
      </div>
    );
  }

  if (error || !herb) {
    return (
      <div className="min-h-screen bg-[#F9FAFB] flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-semibold text-[#191F28] mb-2">
            {error || '제품을 찾을 수 없습니다'}
          </h2>
          <Link to="/">
            <Button className="mt-4 bg-[#059669] hover:bg-[#047857]">
              목록으로 돌아가기
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  const handleQuantityChange = (delta: number) => {
    setQuantity(Math.max(1, quantity + delta));
  };

  const stock = stockStatusConfig[herb.stockStatus] || stockStatusConfig.high;

  // 카테고리 텍스트 생성
  const categoryText = [
    herb.marketType === 'domestic' ? '국내 약재' : herb.marketType === 'imported' ? '수입 약재' : '',
    herb.grade,
  ].filter(Boolean).join(' > ') || '한약재';

  return (
    <div className="min-h-screen bg-[#F9FAFB]">
      {/* Navigation Bar */}
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-[1600px] mx-auto px-6 py-4">
          <div className="flex items-center justify-between gap-6">
            <Link to="/">
              <h1 className="text-3xl font-bold cursor-pointer transition-colors">
                <span className="text-[#059669] hover:text-[#047857]">Palantiny</span>
              </h1>
            </Link>

            <div className="flex-1 max-w-2xl">
              <div className="relative">
                <Input
                  placeholder="한약재 제품 검색..."
                  className="w-full h-11 pl-4 pr-12 border-gray-300 rounded-[12px]"
                />
                <Button className="absolute right-1 top-1/2 -translate-y-1/2 h-9 px-4 bg-[#059669] hover:bg-[#047857] text-white rounded-[8px]">
                  <Search className="w-4 h-4" />
                </Button>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <Link to="/mypage">
                <Button variant="ghost" size="sm" className="text-gray-600 hover:text-[#059669]">
                  <User className="w-5 h-5" />
                </Button>
              </Link>
              <Button variant="ghost" size="sm" className="text-gray-600 hover:text-[#059669]">
                <Heart className="w-5 h-5" />
              </Button>
              <Button variant="ghost" size="sm" className="text-gray-600 hover:text-[#059669]">
                <Bell className="w-5 h-5" />
              </Button>
              <Button variant="ghost" size="sm" className="relative text-gray-600 hover:text-[#059669]">
                <ShoppingCart className="w-5 h-5" />
                <span className="absolute -top-1 -right-1 bg-[#059669] text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
                  0
                </span>
              </Button>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <div className="max-w-[1000px] mx-auto px-6 py-6">
        <Link to="/">
          <Button variant="ghost" className="mb-6 text-gray-600 hover:text-[#191F28] hover:bg-gray-100">
            <ArrowLeft className="w-4 h-4 mr-2" />
            목록으로 돌아가기
          </Button>
        </Link>

        <div className="grid grid-cols-[1fr_360px] gap-6 items-start">
          {/* Left Column */}
          <div className="space-y-6">
            {/* Image Section */}
            <div className="bg-white rounded-[12px] border border-gray-200 p-6">
              <div className="w-full aspect-square rounded-[8px] overflow-hidden bg-gray-100 flex items-center justify-center">
                <Leaf className="w-32 h-32 text-[#059669]/20" />
              </div>
            </div>

            {/* Product Specification */}
            <div className="bg-white rounded-[12px] border border-gray-200 p-6">
              <h2 className="text-xl font-bold text-[#191F28] mb-6">약재 상세 정보</h2>

              <div className="space-y-4">
                {herb.manufacturer && (
                  <div className="flex border-b border-gray-100 pb-3">
                    <div className="w-32 text-sm font-medium text-gray-600">제조사</div>
                    <div className="flex-1 text-sm text-[#191F28]">{herb.manufacturer}</div>
                  </div>
                )}
                {herb.origin && (
                  <div className="flex border-b border-gray-100 pb-3">
                    <div className="w-32 text-sm font-medium text-gray-600">원산지</div>
                    <div className="flex-1 text-sm text-[#191F28]">{herb.origin}</div>
                  </div>
                )}
                {herb.packagingUnitG && (
                  <div className="flex border-b border-gray-100 pb-3">
                    <div className="w-32 text-sm font-medium text-gray-600">포장단위</div>
                    <div className="flex-1 text-sm text-[#191F28]">{herb.packagingUnitG}g</div>
                  </div>
                )}
                {herb.pricePerGeun && (
                  <div className="flex border-b border-gray-100 pb-3">
                    <div className="w-32 text-sm font-medium text-gray-600">근당 가격</div>
                    <div className="flex-1 text-sm text-[#191F28]">₩{Number(herb.pricePerGeun).toLocaleString()}</div>
                  </div>
                )}
                {herb.boxQuantity && (
                  <div className="flex border-b border-gray-100 pb-3">
                    <div className="w-32 text-sm font-medium text-gray-600">박스 수량</div>
                    <div className="flex-1 text-sm text-[#191F28]">{herb.boxQuantity}</div>
                  </div>
                )}
                {herb.subscriptionPrice && (
                  <div className="flex border-b border-gray-100 pb-3">
                    <div className="w-32 text-sm font-medium text-gray-600">구독 가격</div>
                    <div className="flex-1 text-sm text-[#191F28]">₩{Number(herb.subscriptionPrice).toLocaleString()}</div>
                  </div>
                )}
                {herb.discountRate && (
                  <div className="flex border-b border-gray-100 pb-3">
                    <div className="w-32 text-sm font-medium text-gray-600">구독 할인율</div>
                    <div className="flex-1 text-sm text-[#191F28]">{herb.discountRate}</div>
                  </div>
                )}
                {herb.warehouseMaker && (
                  <div className="flex border-b border-gray-100 pb-3">
                    <div className="w-32 text-sm font-medium text-gray-600">입고 업체</div>
                    <div className="flex-1 text-sm text-[#191F28]">{herb.warehouseMaker}</div>
                  </div>
                )}
                {herb.warehouseDate && (
                  <div className="flex border-b border-gray-100 pb-3">
                    <div className="w-32 text-sm font-medium text-gray-600">입고일</div>
                    <div className="flex-1 text-sm text-[#191F28]">{herb.warehouseDate}</div>
                  </div>
                )}
                {herb.warehouseExpired && (
                  <div className="flex pb-3">
                    <div className="w-32 text-sm font-medium text-gray-600">유통기한</div>
                    <div className="flex-1 text-sm text-[#191F28]">{herb.warehouseExpired}</div>
                  </div>
                )}
              </div>
            </div>

            {/* 한의학 정보 (성, 미, 귀경, 사상) */}
            {(herb.nature || herb.taste || herb.meridian || herb.constitution) && (
              <div className="bg-white rounded-[12px] border border-gray-200 p-6">
                <h2 className="text-xl font-bold text-[#191F28] mb-6">한의학 정보</h2>
                <div className="space-y-4">
                  {herb.nature && (
                    <div className="flex border-b border-gray-100 pb-3">
                      <div className="w-32 text-sm font-medium text-gray-600">성 (性)</div>
                      <div className="flex-1 text-sm text-[#191F28]">{herb.nature}</div>
                    </div>
                  )}
                  {herb.taste && (
                    <div className="flex border-b border-gray-100 pb-3">
                      <div className="w-32 text-sm font-medium text-gray-600">미 (味)</div>
                      <div className="flex-1 text-sm text-[#191F28]">{herb.taste}</div>
                    </div>
                  )}
                  {herb.meridian && (
                    <div className="flex border-b border-gray-100 pb-3">
                      <div className="w-32 text-sm font-medium text-gray-600">귀경 (歸經)</div>
                      <div className="flex-1 text-sm text-[#191F28]">{herb.meridian}</div>
                    </div>
                  )}
                  {herb.constitution && (
                    <div className="flex pb-3">
                      <div className="w-32 text-sm font-medium text-gray-600">사상 (四象)</div>
                      <div className="flex-1 text-sm text-[#191F28]">{herb.constitution}</div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 약재 설명 */}
            {(herb.description || herb.feature || herb.property) && (
              <div className="bg-white rounded-[12px] border border-gray-200 p-6">
                <h2 className="text-xl font-bold text-[#191F28] mb-6">약재 설명</h2>
                <div className="space-y-4">
                  {herb.description && (
                    <div>
                      <h3 className="text-sm font-medium text-gray-600 mb-1">설명</h3>
                      <p className="text-sm text-[#191F28] leading-relaxed">{herb.description}</p>
                    </div>
                  )}
                  {herb.feature && (
                    <div>
                      <h3 className="text-sm font-medium text-gray-600 mb-1">특징</h3>
                      <p className="text-sm text-[#191F28] leading-relaxed">{herb.feature}</p>
                    </div>
                  )}
                  {herb.property && (
                    <div>
                      <h3 className="text-sm font-medium text-gray-600 mb-1">가공 특성</h3>
                      <p className="text-sm text-[#191F28] leading-relaxed">{herb.property}</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 주의사항 */}
            {(herb.interaction || herb.note) && (
              <div className="bg-white rounded-[12px] border border-gray-200 p-6">
                <h2 className="text-xl font-bold text-[#191F28] mb-6">주의사항</h2>
                <div className="space-y-4">
                  {herb.interaction && (
                    <div>
                      <h3 className="text-sm font-medium text-gray-600 mb-1">상호작용</h3>
                      <p className="text-sm text-[#191F28] leading-relaxed">{herb.interaction}</p>
                    </div>
                  )}
                  {herb.note && (
                    <div>
                      <h3 className="text-sm font-medium text-gray-600 mb-1">비고</h3>
                      <p className="text-sm text-[#191F28] leading-relaxed">{herb.note}</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 안심 확인 서비스 */}
            <div className="bg-gradient-to-br from-[#059669]/5 to-white rounded-[12px] border border-[#059669]/20 p-6">
              <div className="flex items-center gap-2 mb-4">
                <Package className="w-5 h-5 text-[#059669]" />
                <h2 className="text-xl font-bold text-[#191F28]">안심 확인 서비스</h2>
              </div>
              <p className="text-sm text-gray-600 mb-4">
                본 제품의 생산 이력과 공식 인증서를 확인하실 수 있습니다.
              </p>
              <Button
                className="w-full h-11 bg-[#059669] hover:bg-[#047857] text-white rounded-[8px] text-sm"
                onClick={() => window.open('https://nikom.or.kr/portal/main/module/premium/view.do?nav_code=mai1729679189&idx=41', '_blank')}
              >
                <FileText className="w-4 h-4 mr-2" />
                한약재 정보제공 사이트 바로가기
              </Button>
            </div>
          </div>

          {/* Right Column - Sticky Product Info & Purchase */}
          <div className="sticky top-6">
            <div className="bg-white rounded-[12px] border border-gray-200 p-6">
              {/* Category */}
              <div className="text-sm text-gray-500 mb-2">{categoryText}</div>

              {/* Product Title */}
              <h1 className="text-xl font-bold text-[#191F28] mb-1">{herb.name}</h1>

              {/* Sub info */}
              {(herb.name_chn || herb.name_eng) && (
                <p className="text-sm text-gray-500 mb-3">
                  {[herb.name_chn, herb.name_eng].filter(Boolean).join(' / ')}
                </p>
              )}

              {/* Description */}
              {herb.description && (
                <p className="text-sm text-gray-600 mb-4 line-clamp-2">{herb.description}</p>
              )}

              <div className="border-t border-gray-200 my-4"></div>

              {/* Price */}
              <div className="mb-4">
                <div className="text-3xl font-bold text-[#059669]">
                  {herb.price ? `₩${herb.price.toLocaleString()}` : '가격 문의'}
                </div>
              </div>

              <div className="border-t border-gray-200 my-4"></div>

              {/* Quantity Selector */}
              <div className="mb-4">
                <label className="text-sm font-medium text-gray-700 mb-2 block">수량</label>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => handleQuantityChange(-1)}
                    className="w-10 h-10 flex items-center justify-center border border-gray-300 rounded-[8px] hover:bg-gray-50 transition-colors"
                  >
                    <Minus className="w-4 h-4" />
                  </button>
                  <input
                    type="text"
                    value={quantity}
                    readOnly
                    className="w-20 h-10 text-center border border-gray-300 rounded-[8px]"
                  />
                  <button
                    onClick={() => handleQuantityChange(1)}
                    className="w-10 h-10 flex items-center justify-center border border-gray-300 rounded-[8px] hover:bg-gray-50 transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Total Price */}
              {herb.price > 0 && (
                <div className="bg-gray-50 rounded-[8px] p-3 mb-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-700">구매 수량 {quantity}개</span>
                    <span className="text-xl font-bold text-[#059669]">
                      ₩{(herb.price * quantity).toLocaleString()}
                    </span>
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="space-y-2 mb-4">
                <Button className="w-full h-12 bg-[#059669] hover:bg-[#047857] text-white rounded-[8px]">
                  바로구매
                </Button>
                <Button variant="outline" className="w-full h-12 border-gray-300 text-gray-700 hover:bg-gray-50 rounded-[8px]">
                  장바구니
                </Button>
              </div>

              <div className="border-t border-gray-200 my-4"></div>

              {/* Delivery Information */}
              <div className="space-y-3">
                <div className="flex items-start justify-between py-2">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#059669]" />
                    <span className="text-sm text-gray-700">재고 상태</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className={`text-sm font-semibold ${stock.color}`}>{stock.label}</span>
                    <ChevronRight className="w-4 h-4 text-gray-400" />
                  </div>
                </div>

                <div className="flex items-start justify-between py-2">
                  <div className="flex items-center gap-2">
                    <Truck className="w-4 h-4 text-gray-600" />
                    <span className="text-sm text-gray-700">일반 배송</span>
                  </div>
                  <div className="flex flex-col items-end">
                    <span className="text-sm font-medium text-[#191F28]">3,000원</span>
                    <span className="text-xs text-gray-500">평균 2-3일 이내 도착</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <ChatbotButton />
    </div>
  );
}
