import Image from 'next/image';
import Link from 'next/link';
import logo from "../../public/assets/img_placeholder/logo-lenie-ai.png";

const LogoDark = () => {
  return (
    <Link href='/'>
      <Image src={logo} alt='AIMass' width='96' height='24' />
    </Link>
  );
};

export default LogoDark;
