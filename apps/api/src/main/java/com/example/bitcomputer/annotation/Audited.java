package com.example.bitcomputer.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 감사 로그에 남겨야 하는 엔드포인트에 붙인다.
 *
 * 처음에는 환자 식별 정보를 다루는 엔드포인트만을 위해 {@code AuditPatientAccess}라는
 * 이름으로 만들어졌지만(I1), 관리자 뮤테이션(직원 생성, 역할 변경, 부서 생성·개명 등
 * 환자 데이터와 무관한 행위)도 감사 대상이 되면서 이름이 실제 쓰임과 맞지 않게 됐다.
 * "누가 권한 구조를 바꿨는가"도 "누가 환자 기록을 봤는가"만큼 감사가 필요하다.
 *
 * AOP 로 전 구간을 자동으로 감싸지 않고 명시적으로 표시하는 이유는, 어떤
 * 엔드포인트가 감사 대상인지가 코드에 드러나게 하기 위해서다. 이 애너테이션이
 * 붙은 목록이 곧 감사 대상 문서가 된다.
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Audited {
    /** 감사 로그에 남길 행위 이름. 예: PATIENT_VIEW, ROLE_CHANGE */
    String action();
}
