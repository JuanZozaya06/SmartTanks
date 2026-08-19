import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    loadComponent: () =>
      import('./dashboard/dashboard.component').then((module) => module.DashboardComponent),
  },
  {
    path: 'history',
    loadComponent: () =>
      import('./history/history.component').then((module) => module.HistoryComponent),
  },
  { path: '**', redirectTo: '' },
];
