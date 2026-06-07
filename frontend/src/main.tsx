import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import './index.css'
import App, { AnalyticsPage } from './App.tsx'
import { DynamicSimulationPage } from './pages/DynamicSimulationPage.tsx'
import { LandingPage } from './pages/LandingPage.tsx'
import { TooltipProvider } from '@/components/ui/tooltip'

const rootRoute = createRootRoute()

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: LandingPage,
})

const dashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/dashboard',
  component: App,
})

const analyticsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/analytics',
  component: AnalyticsPage,
})

const dynamicRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/dynamic',
  component: DynamicSimulationPage,
})

const router = createRouter({
  routeTree: rootRoute.addChildren([indexRoute, dashboardRoute, analyticsRoute, dynamicRoute]),
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <TooltipProvider>
      <RouterProvider router={router} />
    </TooltipProvider>
  </StrictMode>,
)
