import { create } from 'zustand';

export interface AuthUser {
  id: number;
  email: string;
  displayName: string;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  balance: number;
  setAuth: (token: string, user: AuthUser) => void;
  setBalance: (b: number) => void;
  logout: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  token: localStorage.getItem('pea_token'),
  user: JSON.parse(localStorage.getItem('pea_user') ?? 'null'),
  balance: 0,
  setAuth: (token, user) => {
    localStorage.setItem('pea_token', token);
    localStorage.setItem('pea_user', JSON.stringify(user));
    set({ token, user });
  },
  setBalance: (balance) => set({ balance }),
  logout: () => {
    localStorage.removeItem('pea_token');
    localStorage.removeItem('pea_user');
    set({ token: null, user: null, balance: 0 });
  },
}));
