import Header_04 from '../header/Header_04';
import Footer_04 from '../footer/Footer_04';

// eslint-disable-next-line react/prop-types
const Wrapper_04 = ({ children }) => {
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
};

export default Wrapper_04;
