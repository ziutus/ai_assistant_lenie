import Header_04 from '@/components/header/Header_04';
import Footer_04 from '@/components/footer/Footer_04';

function Wrapper04({ children }) {
  return (
    <div className='page-wrapper relative z-[1] bg-black text-white'>
      {/*...::: Header Start :::... */}
      <Header_04 />
      {/*...::: Header End :::... */}

      {/*...::: Main Start :::... */}
      {children}
      {/*...::: Main End :::... */}

      {/*...::: Footer Start :::... */}
      <Footer_04 />
      {/*...::: Footer End :::... */}
    </div>
  );
}

export default Wrapper04;
