/*
 * Cambia Icona - Utility offline con interfaccia grafica per Windows.
 *
 * Sostituisce l'icona di un file eseguibile (.exe) o di una DLL usando
 * esclusivamente le API ufficiali di Windows per l'aggiornamento delle
 * risorse (BeginUpdateResource / UpdateResource / EndUpdateResource).
 *
 * Non richiede connessione a Internet, non installa nulla e non modifica
 * il sistema: agisce solo sul file scelto dall'utente.
 */

#include <windows.h>
#include <commctrl.h>
#include <commdlg.h>
#include <shlwapi.h>
#include <shlobj.h>
#include <stdio.h>

/* --- Struttura dei file .ico e delle risorse icona nei PE --- */
#pragma pack(push, 2)
typedef struct {
    BYTE  bWidth;
    BYTE  bHeight;
    BYTE  bColorCount;
    BYTE  bReserved;
    WORD  wPlanes;
    WORD  wBitCount;
    DWORD dwBytesInRes;
    DWORD dwImageOffset;   /* offset nel file .ico */
} ICONDIRENTRY;

typedef struct {
    WORD         idReserved;
    WORD         idType;
    WORD         idCount;
    ICONDIRENTRY idEntries[1];
} ICONDIR;

typedef struct {
    BYTE  bWidth;
    BYTE  bHeight;
    BYTE  bColorCount;
    BYTE  bReserved;
    WORD  wPlanes;
    WORD  wBitCount;
    DWORD dwBytesInRes;
    WORD  nID;             /* id della risorsa RT_ICON */
} GRPICONDIRENTRY;

typedef struct {
    WORD            idReserved;
    WORD            idType;
    WORD            idCount;
    GRPICONDIRENTRY idEntries[1];
} GRPICONDIR;
#pragma pack(pop)

/* --- Identificatori dei controlli --- */
#define IDC_EXE_EDIT   1001
#define IDC_EXE_BROWSE 1002
#define IDC_ICO_EDIT   1003
#define IDC_ICO_BROWSE 1004
#define IDC_APPLY      1005
#define IDC_STATUS     1006
#define IDC_PREVIEW    1007

#define GROUP_ICON_ID  1    /* id del gruppo icona principale di un eseguibile */

static HWND g_hExeEdit, g_hIcoEdit, g_hStatus, g_hPreview;
static HICON g_hPreviewIcon = NULL;

/* Legge l'intero contenuto di un file in un buffer allocato con malloc. */
static BYTE *read_file(const wchar_t *path, DWORD *outSize)
{
    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL,
                           OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE)
        return NULL;

    DWORD size = GetFileSize(h, NULL);
    if (size == INVALID_FILE_SIZE || size == 0) {
        CloseHandle(h);
        return NULL;
    }

    BYTE *buf = (BYTE *)malloc(size);
    if (!buf) {
        CloseHandle(h);
        return NULL;
    }

    DWORD got = 0;
    if (!ReadFile(h, buf, size, &got, NULL) || got != size) {
        free(buf);
        CloseHandle(h);
        return NULL;
    }
    CloseHandle(h);

    if (outSize)
        *outSize = size;
    return buf;
}

static void set_status(const wchar_t *msg)
{
    SetWindowTextW(g_hStatus, msg);
}

/*
 * Sostituisce il gruppo icona principale dell'eseguibile di destinazione
 * con il contenuto del file .ico indicato.
 *
 * Restituisce TRUE in caso di successo; altrimenti scrive un messaggio di
 * errore nel buffer err.
 */
static BOOL replace_icon(const wchar_t *exePath, const wchar_t *icoPath,
                         wchar_t *err, size_t errLen)
{
    DWORD icoSize = 0;
    BYTE *ico = read_file(icoPath, &icoSize);
    if (!ico) {
        _snwprintf(err, errLen, L"Impossibile leggere il file .ico scelto.");
        return FALSE;
    }

    if (icoSize < sizeof(ICONDIR)) {
        free(ico);
        _snwprintf(err, errLen, L"Il file icona non e' valido.");
        return FALSE;
    }

    ICONDIR *dir = (ICONDIR *)ico;
    if (dir->idReserved != 0 || dir->idType != 1 || dir->idCount == 0) {
        free(ico);
        _snwprintf(err, errLen, L"Formato .ico non riconosciuto.");
        return FALSE;
    }

    WORD count = dir->idCount;
    /* Verifica che la directory delle immagini stia nel buffer. */
    if ((size_t)6 + (size_t)count * sizeof(ICONDIRENTRY) > icoSize) {
        free(ico);
        _snwprintf(err, errLen, L"File icona troncato o danneggiato.");
        return FALSE;
    }

    /* Costruisce la risorsa RT_GROUP_ICON a partire dagli ingressi del .ico. */
    size_t grpSize = 6 + (size_t)count * sizeof(GRPICONDIRENTRY);
    GRPICONDIR *grp = (GRPICONDIR *)calloc(1, grpSize);
    if (!grp) {
        free(ico);
        _snwprintf(err, errLen, L"Memoria insufficiente.");
        return FALSE;
    }
    grp->idReserved = 0;
    grp->idType = 1;
    grp->idCount = count;

    /* Convalida ogni immagine prima di toccare l'eseguibile. */
    for (WORD i = 0; i < count; i++) {
        ICONDIRENTRY *e = &dir->idEntries[i];
        if ((size_t)e->dwImageOffset + e->dwBytesInRes > icoSize ||
            e->dwBytesInRes == 0) {
            free(grp);
            free(ico);
            _snwprintf(err, errLen, L"Immagine %u del file icona non valida.", (unsigned)(i + 1));
            return FALSE;
        }
        GRPICONDIRENTRY *g = &grp->idEntries[i];
        g->bWidth      = e->bWidth;
        g->bHeight     = e->bHeight;
        g->bColorCount = e->bColorCount;
        g->bReserved   = e->bReserved;
        g->wPlanes     = e->wPlanes;
        g->wBitCount   = e->wBitCount;
        g->dwBytesInRes = e->dwBytesInRes;
        g->nID         = (WORD)(i + 1);   /* id risorsa RT_ICON */
    }

    HANDLE hUpd = BeginUpdateResourceW(exePath, FALSE);
    if (!hUpd) {
        free(grp);
        free(ico);
        _snwprintf(err, errLen,
                   L"Impossibile aprire l'eseguibile in scrittura.\n"
                   L"Verifica che il file non sia in uso e che tu abbia i permessi.");
        return FALSE;
    }

    BOOL ok = TRUE;

    /* Scrive ciascuna immagine come risorsa RT_ICON con id 1..count. */
    for (WORD i = 0; i < count && ok; i++) {
        ICONDIRENTRY *e = &dir->idEntries[i];
        if (!UpdateResourceW(hUpd, RT_ICON, MAKEINTRESOURCEW(i + 1),
                             MAKELANGID(LANG_NEUTRAL, SUBLANG_NEUTRAL),
                             ico + e->dwImageOffset, e->dwBytesInRes)) {
            ok = FALSE;
        }
    }

    /* Scrive il gruppo icona principale (id 1). */
    if (ok) {
        if (!UpdateResourceW(hUpd, RT_GROUP_ICON, MAKEINTRESOURCEW(GROUP_ICON_ID),
                             MAKELANGID(LANG_NEUTRAL, SUBLANG_NEUTRAL),
                             grp, (DWORD)grpSize)) {
            ok = FALSE;
        }
    }

    if (!EndUpdateResourceW(hUpd, !ok)) {
        /* Se il commit fallisce ma l'aggiornamento era riuscito, segnaliamo errore. */
        if (ok)
            ok = FALSE;
    }

    free(grp);
    free(ico);

    if (!ok) {
        _snwprintf(err, errLen,
                   L"Errore durante la scrittura delle risorse nell'eseguibile.");
        return FALSE;
    }

    /*
     * Avvisa la shell di Windows che l'icona del file e' cambiata, cosi' il
     * desktop, la barra delle applicazioni e la cache icone si aggiornino
     * senza bisogno di riavviare Explorer.
     */
    SHChangeNotify(SHCNE_UPDATEITEM, SHCNF_PATHW | SHCNF_FLUSH, exePath, NULL);
    SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST | SHCNF_FLUSH, NULL, NULL);

    return TRUE;
}

/* Aggiorna l'anteprima dell'icona scelta. */
static void update_preview(const wchar_t *icoPath)
{
    if (g_hPreviewIcon) {
        DestroyIcon(g_hPreviewIcon);
        g_hPreviewIcon = NULL;
    }
    if (icoPath && icoPath[0]) {
        g_hPreviewIcon = (HICON)LoadImageW(NULL, icoPath, IMAGE_ICON, 64, 64,
                                           LR_LOADFROMFILE);
    }
    SendMessageW(g_hPreview, STM_SETICON, (WPARAM)g_hPreviewIcon, 0);
}

/* Mostra una finestra di scelta file e restituisce il percorso. */
static BOOL browse_file(HWND owner, const wchar_t *filter, wchar_t *out, DWORD outLen)
{
    OPENFILENAMEW ofn;
    ZeroMemory(&ofn, sizeof(ofn));
    out[0] = L'\0';
    ofn.lStructSize = sizeof(ofn);
    ofn.hwndOwner = owner;
    ofn.lpstrFilter = filter;
    ofn.lpstrFile = out;
    ofn.nMaxFile = outLen;
    ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_EXPLORER;
    return GetOpenFileNameW(&ofn);
}

static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam)
{
    switch (msg) {
    case WM_CREATE: {
        HINSTANCE hInst = ((LPCREATESTRUCT)lParam)->hInstance;

        CreateWindowW(L"STATIC", L"File eseguibile (.exe / .dll) da modificare:",
                      WS_CHILD | WS_VISIBLE, 15, 15, 440, 18, hwnd, NULL, hInst, NULL);
        g_hExeEdit = CreateWindowW(L"EDIT", L"",
                      WS_CHILD | WS_VISIBLE | WS_BORDER | ES_AUTOHSCROLL,
                      15, 35, 360, 24, hwnd, (HMENU)IDC_EXE_EDIT, hInst, NULL);
        CreateWindowW(L"BUTTON", L"Sfoglia...",
                      WS_CHILD | WS_VISIBLE, 385, 34, 90, 26, hwnd,
                      (HMENU)IDC_EXE_BROWSE, hInst, NULL);

        CreateWindowW(L"STATIC", L"Nuova icona (.ico):",
                      WS_CHILD | WS_VISIBLE, 15, 75, 440, 18, hwnd, NULL, hInst, NULL);
        g_hIcoEdit = CreateWindowW(L"EDIT", L"",
                      WS_CHILD | WS_VISIBLE | WS_BORDER | ES_AUTOHSCROLL,
                      15, 95, 360, 24, hwnd, (HMENU)IDC_ICO_EDIT, hInst, NULL);
        CreateWindowW(L"BUTTON", L"Sfoglia...",
                      WS_CHILD | WS_VISIBLE, 385, 94, 90, 26, hwnd,
                      (HMENU)IDC_ICO_BROWSE, hInst, NULL);

        CreateWindowW(L"STATIC", L"Anteprima:",
                      WS_CHILD | WS_VISIBLE, 15, 135, 100, 18, hwnd, NULL, hInst, NULL);
        g_hPreview = CreateWindowW(L"STATIC", L"",
                      WS_CHILD | WS_VISIBLE | SS_ICON | SS_CENTERIMAGE,
                      15, 155, 72, 72, hwnd, (HMENU)IDC_PREVIEW, hInst, NULL);

        CreateWindowW(L"BUTTON", L"Applica nuova icona",
                      WS_CHILD | WS_VISIBLE | BS_DEFPUSHBUTTON,
                      255, 170, 220, 40, hwnd, (HMENU)IDC_APPLY, hInst, NULL);

        g_hStatus = CreateWindowW(L"STATIC",
                      L"Scegli un eseguibile e un file .ico, poi premi Applica.",
                      WS_CHILD | WS_VISIBLE, 15, 240, 460, 40, hwnd,
                      (HMENU)IDC_STATUS, hInst, NULL);
        return 0;
    }

    case WM_COMMAND: {
        switch (LOWORD(wParam)) {
        case IDC_EXE_BROWSE: {
            wchar_t path[MAX_PATH];
            if (browse_file(hwnd,
                    L"Eseguibili e librerie (*.exe;*.dll)\0*.exe;*.dll\0Tutti i file (*.*)\0*.*\0",
                    path, MAX_PATH)) {
                SetWindowTextW(g_hExeEdit, path);
            }
            return 0;
        }
        case IDC_ICO_BROWSE: {
            wchar_t path[MAX_PATH];
            if (browse_file(hwnd, L"File icona (*.ico)\0*.ico\0Tutti i file (*.*)\0*.*\0",
                            path, MAX_PATH)) {
                SetWindowTextW(g_hIcoEdit, path);
                update_preview(path);
            }
            return 0;
        }
        case IDC_APPLY: {
            wchar_t exe[MAX_PATH], ico[MAX_PATH], err[512];
            GetWindowTextW(g_hExeEdit, exe, MAX_PATH);
            GetWindowTextW(g_hIcoEdit, ico, MAX_PATH);

            if (!exe[0] || !ico[0]) {
                set_status(L"Seleziona sia l'eseguibile che il file .ico.");
                return 0;
            }
            if (!PathFileExistsW(exe)) {
                set_status(L"L'eseguibile indicato non esiste.");
                return 0;
            }
            if (!PathFileExistsW(ico)) {
                set_status(L"Il file .ico indicato non esiste.");
                return 0;
            }

            set_status(L"Operazione in corso...");
            UpdateWindow(g_hStatus);

            if (replace_icon(exe, ico, err, 512)) {
                set_status(L"Icona sostituita con successo.\n"
                           L"Se su desktop vedi ancora la vecchia icona, aggiorna (F5) o riavvia il PC.");
                MessageBoxW(hwnd, L"Icona sostituita correttamente.",
                            L"Operazione completata", MB_OK | MB_ICONINFORMATION);
            } else {
                set_status(err);
                MessageBoxW(hwnd, err, L"Errore", MB_OK | MB_ICONERROR);
            }
            return 0;
        }
        }
        return 0;
    }

    case WM_CTLCOLORSTATIC: {
        HDC hdc = (HDC)wParam;
        SetBkMode(hdc, TRANSPARENT);
        return (LRESULT)GetSysColorBrush(COLOR_BTNFACE);
    }

    case WM_DESTROY:
        if (g_hPreviewIcon)
            DestroyIcon(g_hPreviewIcon);
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, msg, wParam, lParam);
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, PWSTR cmd, int show)
{
    (void)hPrev; (void)cmd;

    INITCOMMONCONTROLSEX icc = { sizeof(icc), ICC_STANDARD_CLASSES };
    InitCommonControlsEx(&icc);

    const wchar_t *cls = L"CambiaIconaWindow";
    WNDCLASSW wc;
    ZeroMemory(&wc, sizeof(wc));
    wc.lpfnWndProc   = WndProc;
    wc.hInstance     = hInst;
    wc.hCursor       = LoadCursor(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.lpszClassName = cls;
    wc.hIcon         = LoadIcon(NULL, IDI_APPLICATION);
    RegisterClassW(&wc);

    HWND hwnd = CreateWindowExW(0, cls, L"Cambia Icona - Utility offline",
                    WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
                    CW_USEDEFAULT, CW_USEDEFAULT, 510, 330,
                    NULL, NULL, hInst, NULL);
    if (!hwnd)
        return 1;

    ShowWindow(hwnd, show);
    UpdateWindow(hwnd);

    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0) > 0) {
        if (!IsDialogMessageW(hwnd, &msg)) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    }
    return 0;
}
