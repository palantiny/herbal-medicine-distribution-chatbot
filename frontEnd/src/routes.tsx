import { createBrowserRouter, Navigate } from 'react-router';
import { BuyerDashboard } from './components/BuyerDashboard';
import { ProductDetail } from './components/ProductDetail';
import { MyPage } from './components/MyPage';

export const router = createBrowserRouter([
  {
    path: '/',
    Component: BuyerDashboard,
    errorElement: <Navigate to="/" replace />,
  },
  {
    path: '/product/:id',
    Component: ProductDetail,
    errorElement: <Navigate to="/" replace />,
  },
  {
    path: '/mypage',
    Component: MyPage,
    errorElement: <Navigate to="/" replace />,
  },
  {
    path: '/buyer',
    element: <Navigate to="/" replace />,
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);