'use client';

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from 'react';
import { createClient } from '@/lib/supabase/client';
import { User, Session } from '@supabase/supabase-js';
import { SupabaseClient } from '@supabase/supabase-js';
import { checkAndInstallSunaAgent } from '@/lib/utils/install-suna-agent';
import { config } from '@/lib/config';

type AuthContextType = {
  supabase: SupabaseClient;
  session: Session | null;
  user: User | null;
  isLoading: boolean;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const supabase = createClient();
  const [session, setSession] = useState<Session | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const getInitialSession = async () => {
      try {
        // If authentication is disabled, provide a mock user for development
        if (config.DISABLE_AUTH) {
          console.log('🔓 Auth disabled - providing mock user for development');
          const mockUser: User = {
            id: 'dev-user-id',
            app_metadata: {},
            user_metadata: {
              name: 'Development User',
              email: 'dev@local.dev',
            },
            aud: 'authenticated',
            created_at: new Date().toISOString(),
            email: 'dev@local.dev',
            email_confirmed_at: new Date().toISOString(),
            last_sign_in_at: new Date().toISOString(),
            phone: '',
            role: 'authenticated',
            updated_at: new Date().toISOString(),
          };

          const mockSession: Session = {
            access_token: 'mock-access-token',
            refresh_token: 'mock-refresh-token',
            expires_in: 3600,
            expires_at: Math.floor(Date.now() / 1000) + 3600,
            token_type: 'bearer',
            user: mockUser,
          };

          setSession(mockSession);
          setUser(mockUser);
          setIsLoading(false);
          return;
        }

        // Normal authentication flow
        const {
          data: { session: currentSession },
        } = await supabase.auth.getSession();
        setSession(currentSession);
        setUser(currentSession?.user ?? null);
      } catch (error) {
      } finally {
        setIsLoading(false);
      }
    };

    getInitialSession();

    // Skip auth state listener when authentication is disabled
    if (config.DISABLE_AUTH) {
      return () => {
        console.log('🔓 Auth disabled - skipping auth state listener cleanup');
      };
    }

    const { data: authListener } = supabase.auth.onAuthStateChange(
      async (event, newSession) => {
        console.log('🔵 Auth state change:', {
          event,
          hasSession: !!newSession,
          hasUser: !!newSession?.user,
          expiresAt: newSession?.expires_at
        });

        setSession(newSession);
        setUser(newSession?.user ?? null);

        if (isLoading) setIsLoading(false);
        switch (event) {
          case 'SIGNED_IN':
            if (newSession?.user) {
              await checkAndInstallSunaAgent(newSession.user.id, newSession.user.created_at);
            }
            break;
          case 'SIGNED_OUT':
            break;
          case 'TOKEN_REFRESHED':
            break;
          case 'MFA_CHALLENGE_VERIFIED':
            break;
          default:
        }
      },
    );

    return () => {
      authListener?.subscription.unsubscribe();
    };
  }, [supabase]); // Removed isLoading from dependencies to prevent infinite loops

  const signOut = async () => {
    try {

      // If authentication is disabled, just clear the mock user
      if (config.DISABLE_AUTH) {
        console.log('🔓 Auth disabled - clearing mock user');
        setSession(null);
        setUser(null);
        return;
      }

      await supabase.auth.signOut();
    } catch (error) {
      console.error('❌ Error signing out:', error);
    }
  };

  const value = {
    supabase,
    session,
    user,
    isLoading,
    signOut,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
