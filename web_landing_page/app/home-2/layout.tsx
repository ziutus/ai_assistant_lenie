import Header_02 from '@/components/header/Header_02';
import Footer_02 from '@/components/footer/Footer_02';

function Wrapper02({ children }) {
  return (
    <div className='page-wrapper relative z-[1] bg-white'>
      {/*...::: Header Start :::... */}
      <Header_02 />
      {/*...::: Header End :::... */}

      {/*...::: Main Start :::... */}
      {children}
      {/*...::: Main End :::... */}

      {/*...::: Footer Start :::... */}
      <Footer_02 />
      {/*...::: Footer End :::... */}
    </div>
  );
}

export default Wrapper02;
