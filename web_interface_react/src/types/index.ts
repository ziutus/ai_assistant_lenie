import type { ApiType } from '@lenie/shared/types';

export type { ApiType, WebDocument, SearchResult, ListItem } from '@lenie/shared/types';
export { emptyDocument, DEFAULT_API_URLS } from '@lenie/shared/types';

export interface AuthorizationState {
  databaseStatus: string;
  setDatabaseStatus: React.Dispatch<React.SetStateAction<string>>;
  vpnServerStatus: string;
  setVpnServerStatus: React.Dispatch<React.SetStateAction<string>>;
  apiKey: string | undefined;
  setApiKey: React.Dispatch<React.SetStateAction<string | undefined>>;
  apiUrl: string;
  setApiUrl: React.Dispatch<React.SetStateAction<string>>;
  apiType: ApiType;
  setApiType: React.Dispatch<React.SetStateAction<ApiType>>;
  sqsLength: number;
  setSqsLength: React.Dispatch<React.SetStateAction<number>>;
  searchInDocument: string;
  setSearchInDocument: React.Dispatch<React.SetStateAction<string>>;
  searchType: string;
  setSearchType: React.Dispatch<React.SetStateAction<string>>;
  selectedDocumentType: string;
  setSelectedDocumentType: React.Dispatch<React.SetStateAction<string>>;
  selectedDocumentState: string;
  setSelectedDocumentState: React.Dispatch<React.SetStateAction<string>>;
}
