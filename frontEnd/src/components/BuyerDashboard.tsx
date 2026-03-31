import { Search, ChevronDown, ChevronUp, User, Heart, Bell, ShoppingCart, Loader2 } from 'lucide-react';
import { ProductCard } from './ProductCard';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Link } from 'react-router';
import { useState, useEffect } from 'react';
import { ChatbotButton } from './ChatbotButton';
import { fetchHerbs, type HerbItem } from '../api';

import defaultHerbImg from 'figma:asset/19e49e0900284b91c8363d4044be913cd97e16b9.png';

// 한글 초성별 카테고리 정의
const initialCategories = [
  { id: 'all', label: '전체', initial: '' },
  { id: 'ga', label: '가', initial: 'ㄱ' },
  { id: 'na-ra', label: '나/다/라', initial: 'ㄴㄷㄹ' },
  { id: 'ma', label: '마', initial: 'ㅁ' },
  { id: 'ba', label: '바', initial: 'ㅂ' },
  { id: 'sa', label: '사', initial: 'ㅅ' },
  { id: 'a', label: '아', initial: 'ㅇ' },
  { id: 'ja', label: '자', initial: 'ㅈ' },
  { id: 'cha', label: '차', initial: 'ㅊ' },
  { id: 'ka-pa', label: '카/타/파', initial: 'ㅋㅌㅍ' },
  { id: 'ha', label: '하', initial: 'ㅎ' },
];

// 한글 초성 추출 함수
const getInitial = (char: string): string => {
  const code = char.charCodeAt(0) - 44032;
  if (code < 0 || code > 11171) return '';
  const initials = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'];
  return initials[Math.floor(code / 588)];
};

// 약재 카테고리 정의
const formCategories = [
  { id: 'root', label: '뿌리류' },
  { id: 'bark', label: '껍질류' },
  { id: 'fruit', label: '열매류' },
  { id: 'flower', label: '꽃류' },
  { id: 'leaf', label: '잎류' },
  { id: 'whole', label: '전초류' },
];

const efficacyCategories = [
  { id: 'tonify-qi', label: '보기약(기운)' },
  { id: 'tonify-blood', label: '보혈약(혈액)' },
  { id: 'tonify-yin', label: '보음약(음기)' },
  { id: 'tonify-yang', label: '보양약(양기)' },
  { id: 'clear-heat', label: '청열약(열내림)' },
  { id: 'dispel-wind', label: '거풍약(바람)' },
];

const originCategories = [
  { id: 'domestic', label: '국내산' },
  { id: 'china', label: '중국산' },
  { id: 'vietnam', label: '베트남산' },
];

// 원산지 표시 텍스트 생성
const getOriginLabel = (origin: string): string => {
  if (!origin) return '';
  const lower = origin.toLowerCase();
  if (lower.includes('국내') || lower.includes('한국') || lower.includes('대한민국')) return '국내산';
  if (lower.includes('중국')) return '중국산';
  if (lower.includes('베트남')) return '베트남산';
  if (lower.includes('인도네시아')) return '인도네시아산';
  return origin;
};

// 원산지 국가명 추출
const getOriginCountry = (origin: string): string => {
  if (!origin) return '';
  const lower = origin.toLowerCase();
  if (lower.includes('국내') || lower.includes('한국') || lower.includes('대한민국')) return '대한민국';
  if (lower.includes('중국')) return '중국';
  if (lower.includes('베트남')) return '베트남';
  if (lower.includes('인도네시아')) return '인도네시아';
  return origin;
};

export function BuyerDashboard() {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedInitial, setSelectedInitial] = useState('all');
  const [selectedForms, setSelectedForms] = useState<string[]>([]);
  const [selectedEfficacies, setSelectedEfficacies] = useState<string[]>([]);
  const [selectedOrigins, setSelectedOrigins] = useState<string[]>([]);
  const [priceRange, setPriceRange] = useState([0, 1000000]);
  const [expandedFilters, setExpandedFilters] = useState({
    initial: true,
    form: true,
    efficacy: true,
    origin: true,
  });
  const [herbs, setHerbs] = useState<HerbItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchHerbs()
      .then((data) => {
        setHerbs(data.herbs);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const toggleFormFilter = (id: string) => {
    setSelectedForms(prev => 
      prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id]
    );
  };

  const toggleEfficacyFilter = (id: string) => {
    setSelectedEfficacies(prev => 
      prev.includes(id) ? prev.filter(e => e !== id) : [...prev, id]
    );
  };

  const toggleOriginFilter = (id: string) => {
    setSelectedOrigins(prev => 
      prev.includes(id) ? prev.filter(o => o !== id) : [...prev, id]
    );
  };

  // 카테고리별 필터링
  const filteredProducts = herbs.filter((herb) => {
    // 검색어 필터
    const matchesSearch = herb.name.toLowerCase().includes(searchTerm.toLowerCase());

    // 한글 자음 필터
    let matchesInitial = true;
    if (selectedInitial !== 'all') {
      const category = initialCategories.find(c => c.id === selectedInitial);
      if (category && category.initial) {
        const herbInitial = getInitial(herb.name[0]);
        matchesInitial = category.initial.includes(herbInitial);
      }
    }

    // 가격 범위 필터
    const matchesPrice = herb.price >= priceRange[0] && herb.price <= priceRange[1];

    // 원산지 필터 (체크박스)
    const originCountry = getOriginCountry(herb.origin);
    const matchesOrigin = selectedOrigins.length === 0 ||
      (selectedOrigins.includes('domestic') && originCountry === '대한민국') ||
      (selectedOrigins.includes('china') && originCountry === '중국') ||
      (selectedOrigins.includes('vietnam') && originCountry === '베트남');

    return matchesSearch && matchesInitial && matchesPrice && matchesOrigin;
  });

  return (
    <div className="min-h-screen bg-[#F9FAFB]">
      {/* Navigation Bar */}
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-[1600px] mx-auto px-6 py-4">
          <div className="flex items-center justify-between gap-6">
            {/* Logo */}
            <Link to="/">
              <h1 className="text-3xl font-bold cursor-pointer transition-colors">
                <span className="text-[#059669] hover:text-[#047857]">Palantiny</span>
              </h1>
            </Link>

            {/* Search Bar - 중앙 */}
            <div className="flex-1 max-w-2xl">
              <div className="relative">
                <Input
                  placeholder="한약재 제품 검색..."
                  className="w-full h-11 pl-4 pr-12 border-gray-300 rounded-[12px]"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
                <Button 
                  className="absolute right-1 top-1/2 -translate-y-1/2 h-9 px-4 bg-[#059669] hover:bg-[#047857] text-white rounded-[8px]"
                >
                  <Search className="w-4 h-4" />
                </Button>
              </div>
            </div>

            {/* Right Side Icons */}
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

      {/* Main Content with Sidebar */}
      <div className="max-w-[1600px] mx-auto px-6 py-6">
        <div className="flex gap-6">
          {/* Left Sidebar - Filters */}
          <div className="w-56 flex-shrink-0">
            <div className="bg-white rounded-[8px] border border-gray-200 overflow-hidden sticky top-6">
              {/* 분류 항목 헤더 */}
              <div className="bg-[#059669] text-white px-4 py-3">
                <h2 className="font-bold text-base">분류 항목</h2>
              </div>

              <div className="p-4">
                {/* 한글 자음 */}
                <div className="mb-4">
                  <button
                    onClick={() => setExpandedFilters({ ...expandedFilters, initial: !expandedFilters.initial })}
                    className="flex items-center justify-between w-full text-sm font-semibold text-[#191F28] mb-2"
                  >
                    <span>한글 자음</span>
                    {expandedFilters.initial ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                  {expandedFilters.initial && (
                    <div className="space-y-1 ml-1">
                      {initialCategories.map((category) => (
                        <label 
                          key={category.id} 
                          className={`flex items-center gap-2.5 cursor-pointer group px-2 py-1.5 rounded-[6px] transition-colors ${
                            selectedInitial === category.id 
                              ? 'bg-[#059669]/5 text-[#059669]' 
                              : 'hover:bg-gray-50 text-gray-700'
                          }`}
                        >
                          <div className="relative flex items-center justify-center">
                            <input
                              type="radio"
                              name="initial"
                              checked={selectedInitial === category.id}
                              onChange={() => setSelectedInitial(category.id)}
                              className="sr-only peer"
                            />
                            <div className={`w-4 h-4 rounded-full border-2 transition-all ${
                              selectedInitial === category.id
                                ? 'border-[#059669] bg-[#059669]'
                                : 'border-gray-300 group-hover:border-[#059669]'
                            }`}>
                              {selectedInitial === category.id && (
                                <div className="w-full h-full flex items-center justify-center">
                                  <div className="w-1.5 h-1.5 bg-white rounded-full"></div>
                                </div>
                              )}
                            </div>
                          </div>
                          <span className={`text-sm transition-colors ${
                            selectedInitial === category.id ? 'font-medium' : ''
                          }`}>
                            {category.label}
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>

                {/* 형상별/부위 */}
                <div className="mb-4 pt-4 border-t border-gray-200">
                  <button
                    onClick={() => setExpandedFilters({ ...expandedFilters, form: !expandedFilters.form })}
                    className="flex items-center justify-between w-full text-sm font-semibold text-[#191F28] mb-2"
                  >
                    <span>형상별/부위</span>
                    {expandedFilters.form ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                  {expandedFilters.form && (
                    <div className="space-y-1 ml-1">
                      {formCategories.map((category) => (
                        <label 
                          key={category.id} 
                          className={`flex items-center gap-2.5 cursor-pointer group px-2 py-1.5 rounded-[6px] transition-colors ${
                            selectedForms.includes(category.id)
                              ? 'bg-[#059669]/5 text-[#059669]'
                              : 'hover:bg-gray-50 text-gray-700'
                          }`}
                        >
                          <div className="relative flex items-center justify-center">
                            <input
                              type="checkbox"
                              checked={selectedForms.includes(category.id)}
                              onChange={() => toggleFormFilter(category.id)}
                              className="sr-only peer"
                            />
                            <div className={`w-4 h-4 rounded transition-all ${
                              selectedForms.includes(category.id)
                                ? 'border-2 border-[#059669] bg-[#059669]'
                                : 'border-2 border-gray-300 group-hover:border-[#059669]'
                            }`}>
                              {selectedForms.includes(category.id) && (
                                <svg className="w-full h-full text-white" viewBox="0 0 16 16" fill="none">
                                  <path d="M13 4L6 11L3 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                                </svg>
                              )}
                            </div>
                          </div>
                          <span className={`text-sm transition-colors ${
                            selectedForms.includes(category.id) ? 'font-medium' : ''
                          }`}>
                            {category.label}
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>

                {/* 효능 */}
                <div className="mb-4 pt-4 border-t border-gray-200">
                  <button
                    onClick={() => setExpandedFilters({ ...expandedFilters, efficacy: !expandedFilters.efficacy })}
                    className="flex items-center justify-between w-full text-sm font-semibold text-[#191F28] mb-2"
                  >
                    <span>효능</span>
                    {expandedFilters.efficacy ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                  {expandedFilters.efficacy && (
                    <div className="space-y-1 ml-1">
                      {efficacyCategories.map((category) => (
                        <label 
                          key={category.id} 
                          className={`flex items-center gap-2.5 cursor-pointer group px-2 py-1.5 rounded-[6px] transition-colors ${
                            selectedEfficacies.includes(category.id)
                              ? 'bg-[#059669]/5 text-[#059669]'
                              : 'hover:bg-gray-50 text-gray-700'
                          }`}
                        >
                          <div className="relative flex items-center justify-center">
                            <input
                              type="checkbox"
                              checked={selectedEfficacies.includes(category.id)}
                              onChange={() => toggleEfficacyFilter(category.id)}
                              className="sr-only peer"
                            />
                            <div className={`w-4 h-4 rounded transition-all ${
                              selectedEfficacies.includes(category.id)
                                ? 'border-2 border-[#059669] bg-[#059669]'
                                : 'border-2 border-gray-300 group-hover:border-[#059669]'
                            }`}>
                              {selectedEfficacies.includes(category.id) && (
                                <svg className="w-full h-full text-white" viewBox="0 0 16 16" fill="none">
                                  <path d="M13 4L6 11L3 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                                </svg>
                              )}
                            </div>
                          </div>
                          <span className={`text-sm transition-colors ${
                            selectedEfficacies.includes(category.id) ? 'font-medium' : ''
                          }`}>
                            {category.label}
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>

                {/* 원산지 */}
                <div className="pt-4 border-t border-gray-200">
                  <button
                    onClick={() => setExpandedFilters({ ...expandedFilters, origin: !expandedFilters.origin })}
                    className="flex items-center justify-between w-full text-sm font-semibold text-[#191F28] mb-2"
                  >
                    <span>원산지</span>
                    {expandedFilters.origin ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                  {expandedFilters.origin && (
                    <div className="space-y-1 ml-1">
                      {originCategories.map((category) => (
                        <label 
                          key={category.id} 
                          className={`flex items-center gap-2.5 cursor-pointer group px-2 py-1.5 rounded-[6px] transition-colors ${
                            selectedOrigins.includes(category.id)
                              ? 'bg-[#059669]/5 text-[#059669]'
                              : 'hover:bg-gray-50 text-gray-700'
                          }`}
                        >
                          <div className="relative flex items-center justify-center">
                            <input
                              type="checkbox"
                              checked={selectedOrigins.includes(category.id)}
                              onChange={() => toggleOriginFilter(category.id)}
                              className="sr-only peer"
                            />
                            <div className={`w-4 h-4 rounded transition-all ${
                              selectedOrigins.includes(category.id)
                                ? 'border-2 border-[#059669] bg-[#059669]'
                                : 'border-2 border-gray-300 group-hover:border-[#059669]'
                            }`}>
                              {selectedOrigins.includes(category.id) && (
                                <svg className="w-full h-full text-white" viewBox="0 0 16 16" fill="none">
                                  <path d="M13 4L6 11L3 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                                </svg>
                              )}
                            </div>
                          </div>
                          <span className={`text-sm transition-colors ${
                            selectedOrigins.includes(category.id) ? 'font-medium' : ''
                          }`}>
                            {category.label}
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Right Content - Products */}
          <div className="flex-1">
            {/* 상단 탭과 정렬 */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Button 
                  className="h-10 px-6 bg-[#059669] hover:bg-[#047857] text-white rounded-[8px] text-sm"
                >
                  모든 항목
                </Button>
                <Button 
                  variant="outline"
                  className="h-10 px-6 border-gray-300 text-gray-700 hover:bg-gray-50 rounded-[8px] text-sm"
                >
                  카테고리별
                </Button>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-600">Sort by:</span>
                <select className="h-10 px-3 border border-gray-300 rounded-[8px] text-sm bg-white text-gray-700">
                  <option>가격순</option>
                  <option>최신순</option>
                  <option>가격 낮은순</option>
                  <option>가격 높은순</option>
                  <option>인기순</option>
                </select>
                <select className="h-10 px-3 border border-gray-300 rounded-[8px] text-sm bg-white text-gray-700">
                  <option>모두</option>
                  <option>국산</option>
                  <option>수입</option>
                </select>
              </div>
            </div>

            {/* Loading / Error */}
            {loading && (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="w-8 h-8 animate-spin text-[#059669]" />
                <span className="ml-3 text-gray-500">약재 목록을 불러오는 중...</span>
              </div>
            )}

            {error && (
              <div className="text-center py-12">
                <p className="text-red-500">{error}</p>
                <Button
                  className="mt-4 bg-[#059669] hover:bg-[#047857] text-white"
                  onClick={() => {
                    setLoading(true);
                    setError(null);
                    fetchHerbs()
                      .then((data) => { setHerbs(data.herbs); setLoading(false); })
                      .catch((err) => { setError(err.message); setLoading(false); });
                  }}
                >
                  다시 시도
                </Button>
              </div>
            )}

            {/* Product Grid - 4 columns */}
            {!loading && !error && (
              <div className="grid grid-cols-4 gap-4">
                {filteredProducts.map((herb) => (
                  <ProductCard
                    key={herb.id}
                    id={herb.id}
                    name={herb.name}
                    origin={getOriginLabel(herb.origin)}
                    price={herb.price}
                    stockStatus={herb.stockStatus}
                    manufacturer={herb.manufacturer}
                    packagingUnitG={herb.packagingUnitG}
                    qty={herb.qty}
                  />
                ))}
              </div>
            )}

            {/* 결과 없을 때 */}
            {!loading && !error && filteredProducts.length === 0 && (
              <div className="text-center py-12">
                <p className="text-gray-500">검색 결과가 없습니다.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Chatbot Floating Button */}
      <ChatbotButton />
    </div>
  );
}