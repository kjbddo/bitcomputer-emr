export const THEME_STORAGE_KEY = "theme";

/**
 * hydration 이전에 동기 실행되어 저장된 테마를 <html> 에 반영한다.
 * 저장값이 없으면 아무 속성도 붙이지 않는다 — prefers-color-scheme 경로가 처리한다.
 * localStorage 접근이 throw 하는 브라우저(프라이빗 모드)를 위해 try/catch 로 감싼다.
 */
export const themeScript = `(function(){try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t);}catch(e){}})()`;
