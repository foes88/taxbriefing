/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // NEXT_PUBLIC_* 는 Next 가 알아서 처리한다 — 클라이언트 번들에는 빌드 시점에 새겨지고,
  // 서버 컴포넌트에서는 요청 시점에 process.env 로 읽힌다.
  //
  // 여기에 env 블록을 두면 서버 코드까지 빌드 시점 값으로 치환되어,
  // 배포 후 환경변수를 고쳐도 서버가 계속 옛 값(localhost)을 보게 된다.
};

export default nextConfig;
