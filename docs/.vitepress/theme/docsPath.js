export function stripSiteBase(path, base = '/') {
  const rawPath = path || '/';
  const prefix = (base || '/').endsWith('/')
    ? (base || '/').slice(0, -1)
    : base || '/';
  if (!prefix) {
    return rawPath.startsWith('/') ? rawPath : `/${rawPath}`;
  }
  let next = rawPath;
  if (next === prefix || next === `${prefix}/`) {
    next = '/';
  } else if (next.startsWith(`${prefix}/`)) {
    next = next.slice(prefix.length);
  }
  if (!next.startsWith('/')) {
    next = `/${next}`;
  }
  return next;
}

export function isEnglishDocsPath(path, base = '/') {
  const pagePath = stripSiteBase(path, base);
  return (
    pagePath === '/en' || pagePath === '/en/' || pagePath.startsWith('/en/')
  );
}

export function isDocsHomePath(path, base = '/') {
  const pagePath = stripSiteBase(path, base);
  return pagePath === '/' || pagePath === '/en' || pagePath === '/en/';
}
