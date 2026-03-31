import { Link } from 'react-router';
import { ShoppingCart, Leaf } from 'lucide-react';

interface ProductCardProps {
  id: string;
  name: string;
  origin: string;
  price: number;
  stockStatus: 'high' | 'medium' | 'low' | 'out';
  image?: string;
  manufacturer?: string;
  packagingUnitG?: string;
  qty?: number;
}

const stockStatusConfig = {
  high: { label: '재고 충분', color: 'text-green-600' },
  medium: { label: '재고 보통', color: 'text-yellow-600' },
  low: { label: '재고 부족', color: 'text-orange-600' },
  out: { label: '품절', color: 'text-red-600' },
};

export function ProductCard({
  id,
  name,
  origin,
  price,
  stockStatus,
  image,
  packagingUnitG,
}: ProductCardProps) {
  const handleBuyClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    alert('바로 구매 기능이 준비 중입니다.');
  };

  const stock = stockStatusConfig[stockStatus] || stockStatusConfig.high;

  return (
    <Link to={`/product/${id}`}>
      <div className="bg-white rounded-[12px] border border-gray-200 shadow-sm hover:shadow-md transition-all overflow-hidden cursor-pointer group">
        {/* Product Image */}
        <div className="w-full aspect-[4/3] overflow-hidden bg-gray-100 flex items-center justify-center">
          {image ? (
            <img
              src={image}
              alt={name}
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            />
          ) : (
            <Leaf className="w-16 h-16 text-[#059669]/30" />
          )}
        </div>

        {/* Product Info */}
        <div className="p-3">
          <h3 className="text-[#191F28] font-semibold text-base mb-1 leading-tight truncate">
            {name}
          </h3>

          {/* Origin & Stock */}
          <div className="flex items-center justify-between text-xs mb-2">
            <span className="text-gray-500">{origin || '원산지 미상'}</span>
            <span className={stock.color}>{stock.label}</span>
          </div>

          {/* Packaging */}
          {packagingUnitG && (
            <div className="text-xs text-gray-400 mb-1">{packagingUnitG}g</div>
          )}

          {/* Price */}
          <div className="mb-3">
            <div className="text-lg font-semibold text-[#059669]">
              {price ? `₩${price.toLocaleString()}` : '가격 문의'}
              {price > 0 && <span className="text-sm font-normal text-gray-500 ml-1">부터</span>}
            </div>
          </div>

          {/* Buttons */}
          <div className="flex gap-2">
            <button
              className="flex-1 py-2 flex items-center justify-center text-sm transition-all text-gray-700 border border-gray-200 rounded-lg hover:text-[#059669] hover:bg-gray-50 hover:border-[#059669]"
            >
              <span>상세정보</span>
            </button>
            <button
              onClick={handleBuyClick}
              className="flex-1 py-2 flex items-center justify-center gap-1.5 text-sm transition-all text-white bg-[#059669] border border-[#059669] rounded-lg hover:bg-[#047857] hover:border-[#047857]"
            >
              <ShoppingCart className="w-4 h-4" />
              <span>바로구매</span>
            </button>
          </div>
        </div>
      </div>
    </Link>
  );
}