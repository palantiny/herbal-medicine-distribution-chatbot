import { useState } from 'react';
import { Link } from 'react-router';
import { Button } from './ui/button';
import { Input } from './ui/input';
import {
  User,
  Bell,
  ShoppingCart,
  Heart,
  Search,
  Package,
  FileText,
  CreditCard,
  Wallet,
  ChevronRight,
  Download,
  Eye,
  XCircle,
  RotateCcw,
  Repeat,
  RefreshCw,
  Trash2,
  Plus,
  Minus,
} from 'lucide-react';
import { ChatbotButton } from './ChatbotButton';

// 이미지 import
import img1 from 'figma:asset/19e49e0900284b91c8363d4044be913cd97e16b9.png';
import img2 from 'figma:asset/a7ff756f68927275d5173e2efd38b483b0992f8d.png';
import img10 from 'figma:asset/28d322bb13587333bb411b6a213566bd07604045.png';
import img4 from 'figma:asset/1e0bcf5e2ebb45de5ee77096c77f066fdd9ca5d3.png';
import img5 from 'figma:asset/e9b24d6b9b12aff3edc3b9eaff8fd1fafd9c0f65.png';
import img3 from 'figma:asset/8f44c24f5c8da37b59e6fac97f8d2adb34dcc866.png';

// Mock 주문 데이터
const mockOrders = [
  {
    id: '1',
    date: '2026.3.3',
    product: '감초',
    productName: '[씨케이] 중국산 씨케이감초 600g',
    price: 48000,
    quantity: 17,
    status: '배송완료',
    statusColor: 'text-gray-600',
    image: img1,
  },
  {
    id: '2',
    date: '2026.2.24',
    product: '마황',
    productName: '[씨케이] 중국산 씨케이마황 450g',
    price: 32000,
    quantity: 17,
    status: '배송중',
    statusColor: 'text-[#059669]',
    image: img2,
  },
  {
    id: '3',
    date: '2026.2.24',
    product: '설복령',
    productName: '[씨케이] 중국산 씨케이설복령 600g',
    price: 33000,
    quantity: 8,
    status: '배송중',
    statusColor: 'text-[#059669]',
    image: img10,
  },
];

// Mock 취소/반품/교환/환불 내역 데이터
const mockCancellations = [
  {
    id: '1',
    date: '2026.2.20',
    type: '반품',
    productName: '[씨케이] 중국산 씨케이백출 500g',
    price: 45000,
    quantity: 10,
    status: '환불완료',
    statusColor: 'text-[#059669]',
    reason: '제품 불량',
    image: img1,
  },
  {
    id: '2',
    date: '2026.2.15',
    type: '교환',
    productName: '[씨케이] 국내산 씨케이복령 800g',
    price: 52000,
    quantity: 5,
    status: '교환완료',
    statusColor: 'text-gray-600',
    reason: '사이즈 변경',
    image: img2,
  },
];

// Mock 장바구니 데이터
const mockCartItems = [
  {
    id: '1',
    productName: '[씨케이] 중국산 씨케이감초 600g',
    price: 48000,
    quantity: 5,
    image: img1,
  },
  {
    id: '2',
    productName: '[씨케이] 중국산 씨케이마황 450g',
    price: 32000,
    quantity: 3,
    image: img2,
  },
  {
    id: '3',
    productName: '[씨케이] 중국산 씨케이설복령 600g',
    price: 33000,
    quantity: 2,
    image: img10,
  },
];

// Mock 세금계산서 데이터
const mockTaxInvoices = [
  {
    id: '1',
    date: '2026.3.5',
    invoiceNumber: 'TAX-2026-0305-001',
    amount: 816000,
    status: '발행완료',
  },
  {
    id: '2',
    date: '2026.2.25',
    invoiceNumber: 'TAX-2026-0225-002',
    amount: 920000,
    status: '발행완료',
  },
];

// Mock 입금 내역 데이터
const mockPayments = [
  {
    id: '1',
    date: '2026.3.4',
    orderNumber: 'ORD-2026-0304-001',
    amount: 816000,
    method: '무통장입금',
    status: '입금완료',
  },
  {
    id: '2',
    date: '2026.2.24',
    orderNumber: 'ORD-2026-0224-002',
    amount: 920000,
    method: '무통장입금',
    status: '입금완료',
  },
];

type MenuTab = 'orders' | 'statements' | 'cancellations' | 'cart' | 'taxInvoices' | 'payments';

export function MyPage() {
  const [activeTab, setActiveTab] = useState<MenuTab>('orders');
  const [selectedYear, setSelectedYear] = useState('2026');

  const years = ['2026', '2025', '2024', '2023', '2022', '2021'];

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

            {/* Search Bar */}
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

            {/* Right Side Icons */}
            <div className="flex items-center gap-4">
              <Button
                variant="ghost"
                size="sm"
                className="text-gray-600 hover:text-[#059669]"
              >
                <User className="w-5 h-5" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-gray-600 hover:text-[#059669]"
              >
                <Heart className="w-5 h-5" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-gray-600 hover:text-[#059669]"
              >
                <Bell className="w-5 h-5" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="relative text-gray-600 hover:text-[#059669]"
              >
                <ShoppingCart className="w-5 h-5" />
                <span className="absolute -top-1 -right-1 bg-[#059669] text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
                  0
                </span>
              </Button>
              <ChatbotButton />
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <div className="max-w-[1200px] mx-auto px-6 py-8">
        <div className="grid grid-cols-[260px_1fr] gap-6">
          {/* Left Sidebar */}
          <div className="space-y-2">
            {/* MY 쇼핑 */}
            <div className="bg-white rounded-[12px] border border-gray-200 p-4">
              <h3 className="text-sm font-bold text-[#191F28] mb-3">주문 관리</h3>
              <div className="space-y-1">
                <button
                  onClick={() => setActiveTab('orders')}
                  className={`w-full text-left px-3 py-2 text-sm rounded-[8px] transition-colors ${
                    activeTab === 'orders'
                      ? 'bg-[#059669]/10 text-[#059669] font-semibold'
                      : 'text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  주문 목록
                </button>
                <button
                  onClick={() => setActiveTab('cancellations')}
                  className={`w-full text-left px-3 py-2 text-sm rounded-[8px] transition-colors ${
                    activeTab === 'cancellations'
                      ? 'bg-[#059669]/10 text-[#059669] font-semibold'
                      : 'text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  취소/반품/교환/환불 내역
                </button>
                <button
                  onClick={() => setActiveTab('cart')}
                  className={`w-full text-left px-3 py-2 text-sm rounded-[8px] transition-colors ${
                    activeTab === 'cart'
                      ? 'bg-[#059669]/10 text-[#059669] font-semibold'
                      : 'text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  장바구니
                </button>
              </div>
            </div>

            {/* MY 세무 */}
            <div className="bg-white rounded-[12px] border border-gray-200 p-4">
              <h3 className="text-sm font-bold text-[#191F28] mb-3">세무 관리</h3>
              <div className="space-y-1">
                <button
                  onClick={() => setActiveTab('statements')}
                  className={`w-full text-left px-3 py-2 text-sm rounded-[8px] transition-colors ${
                    activeTab === 'statements'
                      ? 'bg-[#059669]/10 text-[#059669] font-semibold'
                      : 'text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  거래명세서
                </button>
                <button
                  onClick={() => setActiveTab('payments')}
                  className={`w-full text-left px-3 py-2 text-sm rounded-[8px] transition-colors ${
                    activeTab === 'payments'
                      ? 'bg-[#059669]/10 text-[#059669] font-semibold'
                      : 'text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  입금 내역
                </button>
                <button
                  onClick={() => setActiveTab('taxInvoices')}
                  className={`w-full text-left px-3 py-2 text-sm rounded-[8px] transition-colors ${
                    activeTab === 'taxInvoices'
                      ? 'bg-[#059669]/10 text-[#059669] font-semibold'
                      : 'text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  세금계산서 발행내역
                </button>
              </div>
            </div>
          </div>

          {/* Right Content Area */}
          <div className="bg-white rounded-[12px] border border-gray-200 p-8">
            {/* Header */}
            <div className="mb-6">
              <h2 className="text-2xl font-bold text-[#191F28]">
                {activeTab === 'orders' && '주문 목록'}
                {activeTab === 'statements' && '거래명세서'}
                {activeTab === 'cancellations' && '취소/반품/교환/환불 내역'}
                {activeTab === 'cart' && '장바구니 목록'}
                {activeTab === 'taxInvoices' && '세금계산서 발행내역'}
                {activeTab === 'payments' && '입금 내역'}
              </h2>
            </div>

            {/* Year Filter */}
            <div className="flex gap-2 mb-6 pb-4 border-b border-gray-200">
              <Button
                size="sm"
                className={`rounded-[20px] px-4 ${
                  selectedYear === 'all'
                    ? 'bg-[#059669] text-white hover:bg-[#047857]'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
                onClick={() => setSelectedYear('all')}
              >
                전체 보기
              </Button>
              {years.map((year) => (
                <Button
                  key={year}
                  size="sm"
                  className={`rounded-[20px] px-4 ${
                    selectedYear === year
                      ? 'bg-[#059669] text-white hover:bg-[#047857]'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                  onClick={() => setSelectedYear(year)}
                >
                  {year}
                </Button>
              ))}
            </div>

            {/* Content based on active tab */}
            {activeTab === 'orders' && (
              <div className="space-y-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-[#191F28]">
                    {selectedYear}.3.3 주문
                  </h3>
                  <button className="text-sm text-[#059669] hover:text-[#047857] font-medium">
                    주문 상세보기 →
                  </button>
                </div>

                {/* Order Cards */}
                {mockOrders.map((order) => (
                  <div
                    key={order.id}
                    className="border border-gray-200 rounded-[12px] p-6"
                  >
                    <div className="flex items-start gap-4">
                      {/* Product Image */}
                      <div className="w-20 h-20 bg-gray-100 rounded-[8px] overflow-hidden">
                        <img
                          src={order.image}
                          alt={order.productName}
                          className="w-full h-full object-cover"
                        />
                      </div>

                      {/* Product Info */}
                      <div className="flex-1">
                        <div className="flex items-start justify-between mb-2">
                          <div>
                            <span
                              className={`inline-block text-sm font-semibold mb-1 ${order.statusColor}`}
                            >
                              {order.status}
                            </span>
                            <h4 className="font-medium text-[#191F28]">
                              {order.productName}
                            </h4>
                            <p className="text-sm text-gray-500 mt-1">
                              {order.quantity}개 | ₩
                              {order.price.toLocaleString()}
                            </p>
                          </div>
                        </div>

                        {/* Action Buttons */}
                        <div className="flex gap-2 mt-4">
                          <Button
                            size="sm"
                            variant="outline"
                            className="border-gray-300 text-gray-700 hover:bg-gray-50 rounded-[8px]"
                          >
                            <Package className="w-4 h-4 mr-1" />
                            배송 조회
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="border-gray-300 text-gray-700 hover:bg-gray-50 rounded-[8px]"
                          >
                            교환·반품 신청
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="border-gray-300 text-gray-700 hover:bg-gray-50 rounded-[8px]"
                          >
                            리뷰 작성하기
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'statements' && (
              <div className="space-y-4">
                <p className="text-gray-600 mb-6">
                  거래명세서를 확인하고 다운로드할 수 있습니다.
                </p>

                {mockOrders.map((order) => (
                  <div
                    key={order.id}
                    className="border border-gray-200 rounded-[12px] p-5 hover:border-[#059669]/30 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <FileText className="w-5 h-5 text-[#059669]" />
                        <div>
                          <h4 className="font-medium text-[#191F28] mb-1">
                            {order.date} 거래명세서
                          </h4>
                          <p className="text-sm text-gray-500">
                            {order.productName} 외 {order.quantity}건
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-lg font-semibold text-[#191F28]">
                          ₩{(order.price * order.quantity).toLocaleString()}
                        </span>
                        <Button
                          size="sm"
                          variant="outline"
                          className="border-gray-300 text-gray-700 hover:bg-gray-50 rounded-[8px] ml-4"
                        >
                          <Eye className="w-4 h-4 mr-1" />
                          보기
                        </Button>
                        <Button
                          size="sm"
                          className="bg-[#059669] hover:bg-[#047857] text-white rounded-[8px]"
                        >
                          <Download className="w-4 h-4 mr-1" />
                          다운로드
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'cancellations' && (
              <div className="space-y-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-[#191F28]">
                    {selectedYear}.2.20 취소/반품/교환/환불
                  </h3>
                  <button className="text-sm text-[#059669] hover:text-[#047857] font-medium">
                    상세보기 →
                  </button>
                </div>

                {/* Cancellation Cards */}
                {mockCancellations.map((cancellation) => (
                  <div
                    key={cancellation.id}
                    className="border border-gray-200 rounded-[12px] p-6"
                  >
                    <div className="flex items-start gap-4">
                      {/* Product Image */}
                      <div className="w-20 h-20 bg-gray-100 rounded-[8px] overflow-hidden">
                        <img
                          src={cancellation.image}
                          alt={cancellation.productName}
                          className="w-full h-full object-cover"
                        />
                      </div>

                      {/* Product Info */}
                      <div className="flex-1">
                        <div className="flex items-start justify-between mb-2">
                          <div>
                            <span
                              className={`inline-block text-sm font-semibold mb-1 ${cancellation.statusColor}`}
                            >
                              {cancellation.status}
                            </span>
                            <h4 className="font-medium text-[#191F28]">
                              {cancellation.productName}
                            </h4>
                            <p className="text-sm text-gray-500 mt-1">
                              {cancellation.quantity}개 | ₩
                              {cancellation.price.toLocaleString()}
                            </p>
                            <p className="text-sm text-gray-500 mt-1">
                              사유: {cancellation.reason}
                            </p>
                          </div>
                        </div>

                        {/* Action Buttons */}
                        <div className="flex gap-2 mt-4">
                          <Button
                            size="sm"
                            variant="outline"
                            className="border-gray-300 text-gray-700 hover:bg-gray-50 rounded-[8px]"
                          >
                            <Package className="w-4 h-4 mr-1" />
                            배송 조회
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="border-gray-300 text-gray-700 hover:bg-gray-50 rounded-[8px]"
                          >
                            교환·반품 신청
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="border-gray-300 text-gray-700 hover:bg-gray-50 rounded-[8px]"
                          >
                            리뷰 작성하기
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'cart' && (
              <div className="space-y-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-[#191F28]">
                    장바구니 목록
                  </h3>
                  <button className="text-sm text-[#059669] hover:text-[#047857] font-medium">
                    상세보기 →
                  </button>
                </div>

                {/* Cart Cards */}
                {mockCartItems.map((item) => (
                  <div
                    key={item.id}
                    className="border border-gray-200 rounded-[12px] p-6"
                  >
                    <div className="flex items-start gap-4">
                      {/* Product Image */}
                      <div className="w-20 h-20 bg-gray-100 rounded-[8px] overflow-hidden">
                        <img
                          src={item.image}
                          alt={item.productName}
                          className="w-full h-full object-cover"
                        />
                      </div>

                      {/* Product Info */}
                      <div className="flex-1">
                        <div className="flex items-start justify-between mb-2">
                          <div>
                            <h4 className="font-medium text-[#191F28]">
                              {item.productName}
                            </h4>
                            <p className="text-sm text-gray-500 mt-1">
                              {item.quantity}개 | ₩
                              {item.price.toLocaleString()}
                            </p>
                          </div>
                        </div>

                        {/* Action Buttons */}
                        <div className="flex gap-2 mt-4">
                          <Button
                            size="sm"
                            variant="outline"
                            className="border-gray-300 text-gray-700 hover:bg-gray-50 rounded-[8px]"
                          >
                            <Package className="w-4 h-4 mr-1" />
                            배송 조회
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="border-gray-300 text-gray-700 hover:bg-gray-50 rounded-[8px]"
                          >
                            교환·반품 신청
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="border-gray-300 text-gray-700 hover:bg-gray-50 rounded-[8px]"
                          >
                            리뷰 작성하기
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'taxInvoices' && (
              <div className="space-y-4">
                <p className="text-gray-600 mb-6">
                  발행된 세금계산서를 확인하고 다운로드할 수 있습니다.
                </p>

                {mockTaxInvoices.map((invoice) => (
                  <div
                    key={invoice.id}
                    className="border border-gray-200 rounded-[12px] p-5 hover:border-[#059669]/30 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <CreditCard className="w-5 h-5 text-[#059669]" />
                        <div>
                          <h4 className="font-medium text-[#191F28] mb-1">
                            {invoice.invoiceNumber}
                          </h4>
                          <p className="text-sm text-gray-500">
                            발행일: {invoice.date} | 상태:{' '}
                            <span className="text-[#059669] font-medium">
                              {invoice.status}
                            </span>
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-lg font-semibold text-[#191F28]">
                          ₩{invoice.amount.toLocaleString()}
                        </span>
                        <Button
                          size="sm"
                          variant="outline"
                          className="border-gray-300 text-gray-700 hover:bg-gray-50 rounded-[8px] ml-4"
                        >
                          <Eye className="w-4 h-4 mr-1" />
                          보기
                        </Button>
                        <Button
                          size="sm"
                          className="bg-[#059669] hover:bg-[#047857] text-white rounded-[8px]"
                        >
                          <Download className="w-4 h-4 mr-1" />
                          다운로드
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'payments' && (
              <div className="space-y-4">
                <p className="text-gray-600 mb-6">
                  입금 내역을 확인할 수 있습니다.
                </p>

                {mockPayments.map((payment) => (
                  <div
                    key={payment.id}
                    className="border border-gray-200 rounded-[12px] p-5 hover:border-[#059669]/30 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <Wallet className="w-5 h-5 text-[#059669]" />
                        <div>
                          <h4 className="font-medium text-[#191F28] mb-1">
                            주문번호: {payment.orderNumber}
                          </h4>
                          <p className="text-sm text-gray-500">
                            입금일: {payment.date} | 결제수단: {payment.method} |
                            상태:{' '}
                            <span className="text-[#059669] font-medium">
                              {payment.status}
                            </span>
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-lg font-semibold text-[#191F28]">
                          ₩{payment.amount.toLocaleString()}
                        </span>
                        <Button
                          size="sm"
                          variant="outline"
                          className="border-gray-300 text-gray-700 hover:bg-gray-50 rounded-[8px] ml-4"
                        >
                          <Eye className="w-4 h-4 mr-1" />
                          상세보기
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}